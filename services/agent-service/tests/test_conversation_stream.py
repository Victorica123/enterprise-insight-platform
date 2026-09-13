from __future__ import annotations

import asyncio
import json
import os
import tempfile
import unittest
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch
from uuid import uuid4

from app import database
from app.auth import ActorPrincipal
from app.chat_events import ChatEventSink, stream_chat_events
from app.chat_service import execute_chat, prepare_chat
from app.config import LLMSettings
from app.conversation_memory import WindowMemory, prepare_memory
from app.conversation_store import (
    ConversationBusy,
    begin_turn,
    finish_turn,
    get_conversation,
    purge_expired_conversations,
    renew_turn,
)
from app.llm_client import _async_stream_completion, close_async_llm_clients
from app.main import app
from app.models import ChatRequest, ChatResponse
from app.rag import delete_document, ingest_document
from app.retrievers import clear_chunk_cache
from fastapi.testclient import TestClient

from tests.test_unified_auth import SECRET, access_token


class ConversationApiTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.db = patch("app.database.DB_PATH", Path(self.temp.name) / "chat.sqlite3")
        self.db.start()
        self.addCleanup(self.db.stop)
        self.environment = patch.dict(os.environ, {
            "AGENT_AUTH_MODE": "jwt", "APP_ENV": "test", "SHARED_JWT_SECRET": SECRET,
            "APP_JWT_ISSUER": "enterprise-insight", "APP_JWT_AUDIENCE": "enterprise-insight-api",
            "LLM_ROUTER_ENABLED": "0",
        })
        self.environment.start()
        self.addCleanup(self.environment.stop)
        clear_chunk_cache()
        self.addCleanup(clear_chunk_cache)
        self.client = TestClient(app)
        self.addCleanup(self.client.close)
        self.document = ingest_document("meeting.md", "客户A的项目延期原因是测试环境部署失败。客户A项目负责人是李四。", tenant_id="tenant-a", owner_id="alice")

    def headers(self, user="alice", tenant="tenant-a", workspace="personal"):
        return {"Authorization": "Bearer " + access_token(sub=user, username=user, tenant_id=tenant, workspace_type=workspace, role="operator")}

    def ask(self, question="客户A的项目为什么延期？", **fields):
        return self.client.post("/chat", headers=self.headers(), json={"question": question, "answer_mode": "local", "workflow_mode": "standard", "retriever_mode": "hybrid", "memory_mode": "window", **fields})

    def test_followup_retrieves_fresh_evidence_and_keeps_original_question(self):
        first = self.ask()
        self.assertEqual(first.status_code, 200, first.text)
        identifier = first.json()["conversation_id"]
        second = self.ask("它的负责人是谁？", conversation_id=identifier)
        self.assertEqual(second.status_code, 200, second.text)
        self.assertIn("李四", second.json()["answer"])
        self.assertTrue(any(step["status"] == "rewritten" for step in second.json()["trace"]))
        history = self.client.get(f"/conversations/{identifier}", headers=self.headers()).json()
        self.assertEqual(history["revision"], 2)
        self.assertEqual(history["turns"][-1]["question"], "它的负责人是谁？")

    def test_followup_suggestions_use_current_evidence_and_skip_the_answered_topic(self):
        for mode in ("window", "summary"):
            for workflow in ("standard", "agentic"):
                with self.subTest(mode=mode, workflow=workflow):
                    first = self.ask(memory_mode=mode, workflow_mode=workflow).json()
                    self.assertEqual(first["follow_up"], ["客户A的负责人是谁？"])
                    second = self.ask("它的负责人是谁？", conversation_id=first["conversation_id"],
                                      memory_mode=mode, workflow_mode=workflow).json()
                    self.assertIn("李四", second["answer"])
                    self.assertEqual(second["follow_up"], [])

    def test_followup_history_is_scoped_to_topics_and_optional(self):
        ingest_document("other.md", "客户B的项目延期原因是审批进展缓慢。客户B项目负责人是王五。",
                        tenant_id="tenant-a", owner_id="alice")
        first = self.ask().json()
        other = self.ask("客户B的负责人是谁？", conversation_id=first["conversation_id"]).json()
        self.assertIn("王五", other["answer"])
        self.assertEqual(other["follow_up"], ["客户B的延期原因是什么？"])
        independent = self.ask("客户A的负责人是谁？", conversation_id=first["conversation_id"],
                               memory_mode="none").json()
        self.assertEqual(independent["follow_up"], ["客户A的延期原因是什么？"])

    def test_followup_stream_skips_recent_questions_like_json(self):
        for endpoint in ("/chat", "/chat/stream"):
            with self.subTest(endpoint=endpoint):
                first = self.ask().json()
                result = self.client.post(endpoint, headers=self.headers(), json={
                    "question": "它的负责人是谁？", "conversation_id": first["conversation_id"],
                    "memory_mode": "window", "answer_mode": "local", "workflow_mode": "standard",
                    "retriever_mode": "hybrid",
                })
                self.assertEqual(result.status_code, 200, result.text)
                if endpoint.endswith("stream"):
                    events = [json.loads(line[6:]) for line in result.text.splitlines() if line.startswith("data: ")]
                    self.assertEqual(events[-1]["type"], "done")
                    response = events[-1]["content"]
                    self.assertEqual(next(event["content"] for event in events if event["type"] == "follow_up"), [])
                else:
                    response = result.json()
                self.assertIn("李四", response["answer"])
                self.assertEqual(response["follow_up"], [])

    def test_refused_answer_with_sources_has_no_followup_suggestions(self):
        response = self.ask("客户A有哪些违约风险？").json()
        self.assertTrue(response["sources"])
        self.assertNotEqual(next(step["status"] for step in response["trace"] if step["name"] == "evidence_check"), "passed")
        self.assertEqual(response["follow_up"], [])

    def test_conversation_id_is_never_authorization(self):
        identifier = self.ask().json()["conversation_id"]
        for headers in (self.headers("bob"), self.headers(tenant="tenant-b")):
            result = self.client.post("/chat", headers=headers, json={"question": "负责人是谁？", "conversation_id": identifier, "memory_mode": "window", "answer_mode": "local"})
            self.assertEqual(result.status_code, 404)
            self.assertEqual(self.client.get(f"/conversations/{identifier}", headers=headers).status_code, 404)

    def test_team_conversation_uses_existing_tenant_sharing_semantics(self):
        first = self.client.post("/chat", headers=self.headers(workspace="team"), json={"question": "客户A项目负责人是谁？", "memory_mode": "window", "answer_mode": "local"})
        identifier = first.json()["conversation_id"]
        other = self.client.post("/chat", headers=self.headers("bob", workspace="team"), json={"question": "它为什么延期？", "conversation_id": identifier, "memory_mode": "window", "answer_mode": "local"})
        self.assertEqual(other.status_code, 200, other.text)
        self.assertIn("环境", other.json()["answer"])

    def test_old_answer_cannot_replace_deleted_evidence(self):
        identifier = self.ask().json()["conversation_id"]
        ingest_document("other.md", "客户B项目负责人是王五。", tenant_id="tenant-a", owner_id="alice")
        delete_document(self.document.document_id, tenant_id="tenant-a", owner_id="alice")
        response = self.ask("它的负责人是谁？", conversation_id=identifier).json()
        self.assertEqual(response["sources"], [])
        self.assertNotIn("李四", response["answer"])
        self.assertNotIn("王五", response["answer"])

    def test_explicit_topics_exclude_other_customers_in_both_workflows(self):
        other = ingest_document("other.md", "客户B项目负责人是王五。", tenant_id="tenant-a", owner_id="alice")
        for workflow in ("standard", "agentic"):
            result = self.ask("客户B的负责人是谁？", workflow_mode=workflow).json()
            self.assertIn("王五", result["answer"])
            self.assertNotIn("李四", result["answer"])
            self.assertEqual({source["document_id"] for source in result["sources"]}, {other.document_id})

    def test_parent_expansion_does_not_restore_an_excluded_customer(self):
        delete_document(self.document.document_id, tenant_id="tenant-a", owner_id="alice")
        database.insert_document("shared", "meeting.md", [
            ("项目进度", "客户A项目负责人是李四。"),
            ("项目进度", "客户B项目负责人是王五。"),
        ], tenant_id="tenant-a", owner_id="alice")
        for workflow in ("standard", "agentic"):
            result = self.ask("客户B的负责人是谁？", workflow_mode=workflow).json()
            self.assertIn("王五", result["answer"])
            self.assertNotIn("李四", result["answer"])
            self.assertTrue(result["sources"])
            self.assertTrue(all("客户A" not in source["content"] for source in result["sources"]))

    def test_lost_lease_returns_conflict_without_releasing_replacement(self):
        replacements = []

        def replace_lease(lease):
            with database.connect() as conn:
                conn.execute("update conversations set lease_until = 0 where conversation_id = ?", (lease.conversation_id,))
            replacements.append(begin_turn(lease.conversation_id, tenant_id="tenant-a", owner_id="alice",
                                           actor_user="alice", exchange_id=str(uuid4())))
            raise ConversationBusy("Conversation lease was replaced; retry this turn.")

        with patch("app.conversation_lease.renew_turn", side_effect=replace_lease):
            response = self.ask()
        self.assertEqual(response.status_code, 409, response.text)
        with database.connect() as conn:
            row = conn.execute("select revision, lease_id from conversations").fetchone()
        self.assertEqual(tuple(row), (0, replacements[0].exchange_id))

    def test_omitted_memory_mode_preserves_stateless_client(self):
        response = self.client.post("/chat", headers=self.headers(), json={"question": "客户A项目负责人是谁？", "answer_mode": "local"})
        self.assertEqual(response.status_code, 200)
        self.assertIsNone(response.json()["conversation_id"])

    def test_stream_finishes_with_json_equivalent_verified_response(self):
        request = {"question": "客户A项目负责人是谁？", "answer_mode": "local", "workflow_mode": "standard"}
        ordinary = self.client.post("/chat", headers=self.headers(), json=request).json()
        streamed = self.client.post("/chat/stream", headers=self.headers(), json=request)
        self.assertEqual(streamed.status_code, 200, streamed.text)
        self.assertIn("text/event-stream", streamed.headers["content-type"])
        events = [json.loads(line[6:]) for line in streamed.text.splitlines() if line.startswith("data: ")]
        self.assertEqual(events[0]["type"], "stage")
        self.assertEqual(events[-1]["type"], "done")
        kinds = [event["type"] for event in events]
        self.assertLess(kinds.index("plan"), kinds.index("delta"))
        self.assertLess(kinds.index("sources"), kinds.index("done"))
        self.assertEqual(events[-1]["content"]["answer"], ordinary["answer"])
        self.assertEqual(events[-1]["content"]["sources"], ordinary["sources"])
        self.assertEqual(events[-1]["content"]["follow_up"], ordinary["follow_up"])
        self.assertEqual(next(event["content"] for event in events if event["type"] == "follow_up"), ordinary["follow_up"])
        self.assertEqual(len({event["exchange_id"] for event in events}), 1)

    def test_stream_checks_jwt_and_egress_before_sending_headers(self):
        self.assertEqual(self.client.post("/chat/stream", json={"question": "hi"}).status_code, 401)
        with patch("app.chat_service.is_model_egress_allowed", return_value=False):
            self.assertEqual(self.client.post("/chat/stream", headers=self.headers(), json={"question": "hi", "answer_mode": "api"}).status_code, 403)

    def test_stream_error_redacts_internal_failure_and_releases_conversation(self):
        with patch("app.routes.chat.answer_question", side_effect=RuntimeError("provider-secret-token")):
            result = self.client.post("/chat/stream", headers=self.headers(), json={"question": "客户A", "answer_mode": "local", "workflow_mode": "standard", "memory_mode": "window"})
        self.assertIn("event: error", result.text)
        self.assertNotIn("provider-secret-token", result.text)
        with database.connect() as conn:
            row = conn.execute("select revision, lease_id, model_calls from conversations").fetchone()
        self.assertEqual(row["revision"], 0)
        self.assertIsNone(row["lease_id"])

    def test_claim_competition_reservation_and_stale_worker_fencing(self):
        lease = begin_turn(None, tenant_id="tenant-a", owner_id="alice", actor_user="alice", exchange_id=str(uuid4()))
        with self.assertRaises(ConversationBusy):
            begin_turn(lease.conversation_id, tenant_id="tenant-a", owner_id="alice", actor_user="alice", exchange_id=str(uuid4()))
        with database.connect() as conn:
            conn.execute("update conversations set lease_until = 0")
        replacement = begin_turn(lease.conversation_id, tenant_id="tenant-a", owner_id="alice", actor_user="alice", exchange_id=str(uuid4()))
        with self.assertRaises(ConversationBusy):
            finish_turn(lease, question="q", rewritten_question="q", response=ChatResponse(answer="stale", sources=[]), model_calls=0, tool_calls=0)
        finish_turn(replacement, question="q", rewritten_question="q", response=None, model_calls=1, tool_calls=0)
        with database.connect() as conn:
            row = conn.execute("select revision, model_calls from conversations").fetchone()
        self.assertEqual(row["revision"], 0)
        self.assertEqual(row["model_calls"], 9)  # Crashed worker's reservation remains charged.

    def test_concurrent_claimers_only_one_succeeds(self):
        identifier = self.ask().json()["conversation_id"]
        def claim(_):
            try:
                return begin_turn(identifier, tenant_id="tenant-a", owner_id="alice", actor_user="alice", exchange_id=str(uuid4()))
            except ConversationBusy:
                return None
        with ThreadPoolExecutor(max_workers=2) as pool:
            results = list(pool.map(claim, range(2)))
        self.assertEqual(sum(result is not None for result in results), 1)

    def test_session_cap_and_summary_window_are_bounded(self):
        identifier = None
        for index in range(10):
            lease = begin_turn(identifier, tenant_id="tenant-a", owner_id="alice", actor_user="alice", exchange_id=str(uuid4()))
            identifier = lease.conversation_id
            finish_turn(lease, question=f"客户A第{index}轮", rewritten_question=f"客户A第{index}轮", response=ChatResponse(answer="not evidence", sources=[]), model_calls=4, tool_calls=0)
        lease = begin_turn(identifier, tenant_id="tenant-a", owner_id="alice", actor_user="alice", exchange_id=str(uuid4()))
        self.assertEqual(lease.limits.max_model_calls, 0)
        memory = prepare_memory("它的负责人是谁？", "summary", lease, allow_model=False)
        self.assertEqual(memory.summary_through, 6)
        self.assertLessEqual(len(memory.summary), 1400)
        self.assertNotIn("not evidence", memory.summary)
        self.assertIn("客户A", memory.question)
        self.assertLessEqual(len(WindowMemory().context([{"rewritten_question": "x" * 2000}] * 10)), 2200)
        self.assertEqual(get_conversation(identifier, tenant_id="tenant-a", owner_id="alice")["revision"], 10)

    def test_live_lease_can_span_many_intervals_but_expired_lease_cannot_renew(self):
        with patch("app.conversation_store.time.time", return_value=1000):
            lease = begin_turn(None, tenant_id="tenant-a", owner_id="alice", actor_user="alice", exchange_id=str(uuid4()))
        for moment in range(1100, 2501, 100):
            with patch("app.conversation_store.time.time", return_value=moment):
                renew_turn(lease)
        with patch("app.conversation_store.time.time", return_value=2700):
            with self.assertRaises(ConversationBusy):
                renew_turn(lease)
        with database.connect() as conn:
            row = conn.execute("select lease_until from conversations where conversation_id = ?", (lease.conversation_id,)).fetchone()
        self.assertEqual(row["lease_until"], 2620)

    def test_retention_skips_in_progress_conversations_then_removes_history(self):
        identifier = self.ask().json()["conversation_id"]
        lease = begin_turn(identifier, tenant_id="tenant-a", owner_id="alice", actor_user="alice", exchange_id=str(uuid4()))
        with database.connect() as conn:
            conn.execute("update conversations set updated_at = '2000-01-01'")
            self.assertEqual(purge_expired_conversations(conn, "2020-01-01", 10, 1), 0)
        finish_turn(lease, question="q", rewritten_question="q", response=None, model_calls=0, tool_calls=0)
        with database.connect() as conn:
            conn.execute("update conversations set updated_at = '2000-01-01'")
            self.assertEqual(purge_expired_conversations(conn, "2020-01-01", 10, 1), 2)
            self.assertEqual(conn.execute("select count(*) from conversation_turns").fetchone()[0], 0)

    def test_comparison_followup_is_not_silently_assigned_to_last_topic(self):
        lease = begin_turn(None, tenant_id="tenant-a", owner_id="alice", actor_user="alice", exchange_id=str(uuid4()))
        finish_turn(lease, question="比较客户A和客户B", rewritten_question="比较客户A和客户B", response=ChatResponse(answer="not evidence", sources=[]), model_calls=0, tool_calls=0)
        lease = begin_turn(lease.conversation_id, tenant_id="tenant-a", owner_id="alice", actor_user="alice", exchange_id=str(uuid4()))
        memory = prepare_memory("它的负责人是谁？", "window", lease, allow_model=False)
        self.assertEqual(memory.question, "它的负责人是谁？")

    def test_summary_cannot_introduce_a_model_invented_topic(self):
        identifier = None
        for _ in range(5):
            lease = begin_turn(identifier, tenant_id="tenant-a", owner_id="alice", actor_user="alice", exchange_id=str(uuid4()))
            identifier = lease.conversation_id
            finish_turn(lease, question="客户A", rewritten_question="客户A", response=ChatResponse(answer="not evidence", sources=[]), model_calls=0, tool_calls=0)
        lease = begin_turn(identifier, tenant_id="tenant-a", owner_id="alice", actor_user="alice", exchange_id=str(uuid4()))
        completion = SimpleNamespace(usage=None, choices=[SimpleNamespace(message=SimpleNamespace(content='{"summary":"客户Z"}'))])
        with patch("app.conversation_memory.is_llm_configured", return_value=True), patch("app.conversation_memory.create_chat_completion", return_value=completion):
            memory = prepare_memory("它的负责人是谁？", "summary", lease, allow_model=True)
        self.assertNotIn("客户Z", memory.summary)
        self.assertIn("客户A", memory.question)
        self.assertIn("rules_fallback", memory.trace.detail)


class ProviderStreamTests(unittest.IsolatedAsyncioTestCase):
    async def asyncTearDown(self):
        await close_async_llm_clients()

    async def test_disconnect_after_first_event_refunds_unused_conversation_budget(self):
        with tempfile.TemporaryDirectory() as directory, patch.object(database, "DB_PATH", Path(directory) / "cancel.sqlite3"):
            prepared = prepare_chat(ChatRequest(question="客户A", answer_mode="local", memory_mode="window"), ActorPrincipal(user_id="alice", tenant_id="tenant-a", role="viewer", workspace_type="personal"))

            def run():
                return execute_chat(prepared, metric_recorder=lambda **_: None,
                                    agentic_handler=lambda *_args, **_kwargs: ChatResponse(answer="q", sources=[]),
                                    standard_handler=lambda *_args, **_kwargs: ChatResponse(answer="q", sources=[]))

            stream = stream_chat_events(run, conversation_id=prepared.conversation_id, exchange_id=prepared.exchange_id)
            await anext(stream)
            await stream.aclose()
            with database.connect() as conn:
                row = conn.execute("select revision, lease_id, model_calls, tool_calls from conversations").fetchone()
            self.assertEqual(tuple(row), (0, None, 0, 0))

    async def test_provider_delta_arrives_before_completion_and_usage_is_retained(self):
        release = asyncio.Event()
        class Stream:
            close = AsyncMock()
            async def __aiter__(self):
                yield SimpleNamespace(choices=[SimpleNamespace(delta=SimpleNamespace(content="首字"))], usage=None)
                await release.wait()
                yield SimpleNamespace(choices=[], usage=SimpleNamespace(prompt_tokens=12, completion_tokens=2))
        stream = Stream()
        client = SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(create=AsyncMock(return_value=stream))), close=AsyncMock())
        sink = ChatEventSink(asyncio.get_running_loop(), None, str(uuid4()))
        settings = LLMSettings("openai", "test", "https://model.test", "unchanged-model", 2, 0)
        with patch("openai.AsyncOpenAI", return_value=client):
            task = asyncio.create_task(_async_stream_completion(settings, [], 0, sink))
            event = await asyncio.wait_for(sink.queue.get(), 1)
            self.assertEqual(event["content"]["text"], "首字")
            self.assertFalse(task.done())
            release.set()
            result = await task
        self.assertEqual(result.usage.prompt_tokens, 12)
        stream.close.assert_awaited_once()
        self.assertEqual(client.chat.completions.create.call_args.kwargs["model"], "unchanged-model")

    async def test_cancellation_closes_provider_stream(self):
        entered = asyncio.Event()
        class Stream:
            close = AsyncMock()
            async def __aiter__(self):
                entered.set()
                await asyncio.Event().wait()
                yield None
        stream = Stream()
        client = SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(create=AsyncMock(return_value=stream))), close=AsyncMock())
        sink = ChatEventSink(asyncio.get_running_loop(), None, str(uuid4()))
        with patch("openai.AsyncOpenAI", return_value=client):
            task = asyncio.create_task(_async_stream_completion(LLMSettings("openai", "test", "https://model.test", "unchanged-model"), [], 0, sink))
            await asyncio.wait_for(entered.wait(), 1)
            task.cancel()
            with self.assertRaises(asyncio.CancelledError):
                await task
        stream.close.assert_awaited_once()


if __name__ == "__main__":
    unittest.main()
