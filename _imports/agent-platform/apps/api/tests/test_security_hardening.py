"""安全加固回归测试。

覆盖 2026-08 加固批次：
- S1 角色校验：documents/embeddings/chat-logs/tool-calls/pending-actions
  的写操作与审计数据不再对 viewer 开放；
- S2 职责分离：发起人（已知身份）不能审批自己的写操作；
- S3 LLM 工具白名单：幻觉工具名不进入执行；
- S4 槽位抽取纠偏：大写工单 ID、模糊目标状态。
"""
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

os.environ.setdefault("LLM_ROUTER_ENABLED", "0")

from fastapi.testclient import TestClient  # noqa: E402

from app.agentic_rag import answer_agentic_question  # noqa: E402
from app.llm_router import LLMJsonResult  # noqa: E402
from app.main import app  # noqa: E402
from app.slot_extraction import extract_target_status, extract_ticket_id  # noqa: E402
from app.tools import execute_tool, resolve_tool_action  # noqa: E402


OPERATOR = {"X-User-Role": "operator"}


class RoleEnforcementTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.db_patcher = patch("app.database.DB_PATH", Path(self.temp_dir.name) / "sec.sqlite3")
        self.db_patcher.start()
        self.client = TestClient(app)

    def tearDown(self) -> None:
        self.db_patcher.stop()
        self.temp_dir.cleanup()

    def test_viewer_cannot_mutate_documents(self) -> None:
        files = {"file": ("a.txt", "客户:测试客户".encode("utf-8"), "text/plain")}
        self.assertEqual(self.client.post("/documents", files=files).status_code, 403)
        self.assertEqual(self.client.delete("/documents/doc-1").status_code, 403)
        self.assertEqual(
            self.client.post("/documents", files=files, headers=OPERATOR).status_code, 200
        )

    def test_viewer_cannot_read_audit_data(self) -> None:
        for endpoint in ("/chat-logs", "/tool-calls", "/pending-actions"):
            self.assertEqual(self.client.get(endpoint).status_code, 403, endpoint)
            self.assertEqual(
                self.client.get(endpoint, headers=OPERATOR).status_code, 200, endpoint
            )
        self.assertEqual(self.client.post("/embeddings/rebuild").status_code, 403)

    def test_metrics_aggregates_stay_open(self) -> None:
        # 聚合指标不含问题原文，viewer 可见（前端监控带依赖）
        self.assertEqual(self.client.get("/metrics/summary").status_code, 200)
        self.assertEqual(self.client.get("/metrics/tools").status_code, 200)


class SeparationOfDutiesTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.db_patcher = patch("app.database.DB_PATH", Path(self.temp_dir.name) / "sod.sqlite3")
        self.db_patcher.start()

    def tearDown(self) -> None:
        self.db_patcher.stop()
        self.temp_dir.cleanup()

    def test_requester_cannot_approve_own_action(self) -> None:
        draft = execute_tool(
            "create_ticket",
            {"title": "t", "description": "d"},
            actor_role="operator",
            actor_user="alice",
        )
        denied = resolve_tool_action(
            draft.pending_action_id, True, actor_role="admin", actor_user="alice"
        )
        self.assertEqual(denied.status, "denied")
        self.assertIn("职责分离", denied.message)

    def test_other_user_can_approve(self) -> None:
        draft = execute_tool(
            "create_ticket",
            {"title": "t", "description": "d"},
            actor_role="operator",
            actor_user="alice",
        )
        approved = resolve_tool_action(
            draft.pending_action_id, True, actor_role="admin", actor_user="bob"
        )
        self.assertEqual(approved.status, "succeeded")

    def test_anonymous_flow_keeps_demo_experience(self) -> None:
        draft = execute_tool("create_ticket", {"title": "t", "description": "d"}, actor_role="operator")
        approved = resolve_tool_action(draft.pending_action_id, True, actor_role="operator")
        self.assertEqual(approved.status, "succeeded")


class LLMToolWhitelistTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.db_patcher = patch("app.database.DB_PATH", Path(self.temp_dir.name) / "wl.sqlite3")
        self.db_patcher.start()

    def tearDown(self) -> None:
        self.db_patcher.stop()
        self.temp_dir.cleanup()

    def test_hallucinated_tool_names_are_filtered(self) -> None:
        fake = LLMJsonResult(
            data=[("drop_database", {}), ("query_tickets", {"status": "open"})],
            prompt_tokens=5,
            completion_tokens=2,
        )
        with patch("app.agentic_rag.llm_select_tool_calls", return_value=fake):
            response = answer_agentic_question("有哪些open工单？", "local", "keyword")
        tool_names = [call.tool_name for call in response.agent_summary.tool_calls]
        self.assertIn("query_tickets", tool_names)
        self.assertNotIn("drop_database", tool_names)
        self.assertTrue(
            any(step.name == "tool_call" and step.status == "filtered" for step in response.trace)
        )


class SlotExtractionTests(unittest.TestCase):
    def test_uppercase_ticket_id_is_normalized(self) -> None:
        self.assertEqual(
            extract_ticket_id("请更新工单 ABCDEF12-3456-78AB 的状态为关闭"),
            "abcdef12-3456-78ab",
        )
        self.assertEqual(extract_ticket_id("没有工单号的问题"), "")

    def test_ambiguous_target_status_is_refused(self) -> None:
        self.assertEqual(extract_target_status("更新一下工单12345678"), "")

    def test_explicit_target_status_still_recognized(self) -> None:
        self.assertEqual(extract_target_status("把工单12345678关闭"), "closed")
        self.assertEqual(extract_target_status("重新打开工单12345678"), "open")


if __name__ == "__main__":
    unittest.main()
