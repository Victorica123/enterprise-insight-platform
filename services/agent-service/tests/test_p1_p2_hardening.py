import tempfile
import threading
import time
import unittest
from dataclasses import replace
from pathlib import Path
from unittest.mock import patch

from app import database
from app.graph_store import get_graph_overview, rebuild_graph
from app.llm_client import clear_llm_client_cache, create_chat_completion
from app.config import LLMSettings
from app.rag import ingest_document, list_documents
from app.retrievers import KeywordRetriever, clear_chunk_cache
from app.ticket_store import list_tickets
from app.tools import execute_tool, get_tool, init_tools, resolve_tool_action


SAMPLE = """# 客户A项目
客户：客户A。项目：升级项目。项目负责人：李四。延期原因：由于网络策略调整，项目延期。
"""


class AtomicKnowledgeWriteTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.db_patcher = patch("app.database.DB_PATH", Path(self.temp_dir.name) / "atomic.sqlite3")
        self.db_patcher.start()
        clear_chunk_cache()

    def tearDown(self) -> None:
        clear_chunk_cache()
        self.db_patcher.stop()
        self.temp_dir.cleanup()

    def test_ingest_rolls_back_document_when_graph_index_fails(self) -> None:
        with patch("app.rag.index_document_graph", side_effect=RuntimeError("graph failed")):
            with self.assertRaisesRegex(RuntimeError, "graph failed"):
                ingest_document("broken.md", SAMPLE)
        self.assertEqual(list_documents(), [])

    def test_graph_rebuild_failure_keeps_previous_graph(self) -> None:
        ingest_document("sample.md", SAMPLE)
        before = get_graph_overview()
        with patch("app.graph_store.extract_graph_from_text", side_effect=RuntimeError("extract failed")):
            with self.assertRaisesRegex(RuntimeError, "extract failed"):
                rebuild_graph()
        after = get_graph_overview()
        self.assertEqual(after["entity_count"], before["entity_count"])
        self.assertEqual(after["relation_count"], before["relation_count"])

    def test_chunk_cache_reloads_only_after_content_revision_changes(self) -> None:
        ingest_document("one.md", SAMPLE)
        clear_chunk_cache()
        with patch("app.retrievers.database.list_chunk_rows", wraps=database.list_chunk_rows) as loader:
            KeywordRetriever().search(["客户A"])
            KeywordRetriever().search(["客户A"])
            self.assertEqual(loader.call_count, 1)
            ingest_document("two.md", SAMPLE.replace("客户A", "客户B"))
            KeywordRetriever().search(["客户B"])
            self.assertEqual(loader.call_count, 2)


class LlmClientPolicyTests(unittest.TestCase):
    def tearDown(self) -> None:
        clear_llm_client_cache()

    def test_client_is_reused_and_request_has_output_budget(self) -> None:
        settings = LLMSettings(
            provider="test",
            api_key="test-key",
            base_url="https://example.invalid/v1",
            model="test-model",
            timeout_seconds=7.5,
            max_retries=1,
            max_completion_tokens=321,
        )
        clear_llm_client_cache()
        with patch("app.llm_client.get_llm_settings", return_value=settings), patch("openai.OpenAI") as factory:
            create_chat_completion(messages=[{"role": "user", "content": "hello"}], temperature=0.1)
            create_chat_completion(messages=[{"role": "user", "content": "again"}], temperature=0.1)

        factory.assert_called_once_with(
            api_key="test-key",
            base_url="https://example.invalid/v1",
            timeout=7.5,
            max_retries=1,
        )
        calls = factory.return_value.chat.completions.create.call_args_list
        self.assertEqual(len(calls), 2)
        self.assertEqual(calls[0].kwargs["max_tokens"], 321)


class ConcurrentApprovalTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.db_patcher = patch("app.database.DB_PATH", Path(self.temp_dir.name) / "approval.sqlite3")
        self.db_patcher.start()
        init_tools()

    def tearDown(self) -> None:
        self.db_patcher.stop()
        self.temp_dir.cleanup()

    def test_only_claim_owner_executes_side_effect(self) -> None:
        tool = get_tool("create_ticket")
        assert tool is not None and tool.approved_handler is not None
        original_handler = tool.approved_handler
        entered = threading.Event()
        executions = 0
        lock = threading.Lock()

        def slow_handler(**payload):
            nonlocal executions
            with lock:
                executions += 1
            entered.set()
            time.sleep(0.15)
            return original_handler(**payload)

        draft = execute_tool(
            "create_ticket",
            {"title": "并发审批", "description": "只允许执行一次", "priority": "high"},
            actor_role="operator",
        )
        results = []

        with patch.dict("app.tools._TOOLS", {"create_ticket": replace(tool, approved_handler=slow_handler)}):
            first = threading.Thread(
                target=lambda: results.append(
                    resolve_tool_action(draft.pending_action_id, True, actor_role="operator")
                )
            )
            second = threading.Thread(
                target=lambda: results.append(
                    resolve_tool_action(draft.pending_action_id, True, actor_role="operator")
                )
            )
            first.start()
            self.assertTrue(entered.wait(timeout=2))
            second.start()
            first.join(timeout=3)
            second.join(timeout=3)

        self.assertEqual(executions, 1)
        self.assertEqual(len(list_tickets()), 1)
        self.assertEqual({result.status for result in results}, {"executing", "succeeded"})
