import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from fastapi.testclient import TestClient

from app.agentic_rag import answer_agentic_question
from app.main import app
from app.ticket_store import (
    create_ticket,
    delete_ticket,
    get_pending_action,
    get_tool_metrics_summary,
    list_pending_actions,
    list_tickets,
    list_tool_call_logs,
)
from app.tools import execute_tool, resolve_tool_action


CREATE_PAYLOAD = {
    "title": "客户 A 延期跟进",
    "description": "测试环境部署失败，需要跟进恢复计划。",
    "priority": "high",
    "assignee": "李四",
    "risk_level": "高",
    "source_document_ids": ["doc-1"],
}


class V3ToolWorkflowTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.db_patcher = patch("app.database.DB_PATH", Path(self.temp_dir.name) / "v3.sqlite3")
        self.db_patcher.start()

    def tearDown(self) -> None:
        self.db_patcher.stop()
        self.temp_dir.cleanup()

    def test_write_is_draft_until_approved_and_executes_exactly_once(self) -> None:
        draft = execute_tool("create_ticket", CREATE_PAYLOAD, actor_role="operator")

        self.assertTrue(draft.success)
        self.assertEqual(draft.status, "pending")
        self.assertEqual(list_tickets(), [])
        self.assertEqual(len(list_pending_actions()), 1)

        first = resolve_tool_action(draft.pending_action_id, True, actor_role="operator")
        tickets_after_first = list_tickets()
        second = resolve_tool_action(draft.pending_action_id, True, actor_role="operator")

        self.assertEqual(first.status, "succeeded")
        self.assertEqual(len(tickets_after_first), 1)
        self.assertEqual(len(list_tickets()), 1)
        self.assertTrue(second.already_resolved)
        self.assertEqual(get_pending_action(draft.pending_action_id).execution_count, 1)
        self.assertEqual(get_tool_metrics_summary()["exact_once_violations"], 0)

    def test_rejection_and_expiry_never_write(self) -> None:
        rejected_draft = execute_tool("create_ticket", CREATE_PAYLOAD, actor_role="operator")
        rejected = resolve_tool_action(rejected_draft.pending_action_id, False, actor_role="operator")
        expired_draft = execute_tool(
            "create_ticket",
            {**CREATE_PAYLOAD, "title": "过期草稿"},
            actor_role="operator",
            approval_ttl_seconds=-1,
        )
        expired = resolve_tool_action(expired_draft.pending_action_id, True, actor_role="operator")

        self.assertEqual(rejected.status, "rejected")
        self.assertEqual(expired.status, "expired")
        self.assertEqual(list_tickets(), [])

    def test_validation_and_permission_are_enforced_and_audited(self) -> None:
        invalid = execute_tool(
            "create_ticket",
            {**CREATE_PAYLOAD, "priority": "super-urgent"},
            actor_role="operator",
        )
        denied = execute_tool("create_ticket", CREATE_PAYLOAD, actor_role="viewer")
        logs = list_tool_call_logs()

        self.assertFalse(invalid.success)
        self.assertEqual(invalid.status, "failed")
        self.assertFalse(denied.success)
        self.assertEqual(denied.status, "denied")
        self.assertEqual(list_pending_actions(), [])
        self.assertEqual({item["status"] for item in logs}, {"failed", "denied"})

    def test_execution_failure_has_final_failed_state_and_log(self) -> None:
        ticket = create_ticket("测试工单", "先创建再删除", status="open")
        draft = execute_tool(
            "update_ticket_status",
            {"ticket_id": ticket.ticket_id, "new_status": "resolved"},
            actor_role="operator",
        )
        delete_ticket(ticket.ticket_id)

        resolution = resolve_tool_action(draft.pending_action_id, True, actor_role="operator")
        action = get_pending_action(draft.pending_action_id)
        log = next(item for item in list_tool_call_logs() if item["action_id"] == draft.pending_action_id)

        self.assertEqual(resolution.status, "failed")
        self.assertEqual(action.status, "failed")
        self.assertEqual(action.execution_count, 1)
        self.assertEqual(log["status"], "failed")
        self.assertTrue(log["error_message"])

    def test_direct_ticket_query_skips_rag(self) -> None:
        create_ticket("查询示例", "直接查询工具不需要知识库", status="open")
        response = answer_agentic_question("有哪些工单？", "local", "hybrid")

        self.assertEqual(response.agent_summary.evidence_status, "not_required")
        self.assertEqual(response.agent_summary.retrieval_rounds, 0)
        self.assertEqual(response.agent_summary.tool_calls[0].tool_name, "query_tickets")
        self.assertIn("共 1 条记录", response.answer)

    def test_api_role_draft_approval_and_metrics_contract(self) -> None:
        client = TestClient(app)
        payload = {
            "title": "API 工单",
            "description": "验证请求体、权限和审批接口。",
            "priority": "medium",
        }
        denied = client.post("/tickets", json=payload, headers={"X-User-Role": "viewer"})
        created = client.post("/tickets", json=payload, headers={"X-User-Role": "operator"})
        ticket_id = created.json()["ticket_id"]
        draft = client.post(
            f"/tickets/{ticket_id}/status-draft",
            json={"new_status": "resolved"},
            headers={"X-User-Role": "operator"},
        )
        action_id = draft.json()["action_id"]
        approved = client.post(
            f"/pending-actions/{action_id}/approve",
            json={"approved": True},
            headers={"X-User-Role": "operator"},
        )
        duplicate = client.post(
            f"/pending-actions/{action_id}/approve",
            json={"approved": True},
            headers={"X-User-Role": "operator"},
        )

        self.assertEqual(denied.status_code, 403)
        self.assertEqual(created.status_code, 200)
        self.assertEqual(draft.status_code, 200)
        self.assertEqual(approved.json()["status"], "succeeded")
        self.assertTrue(duplicate.json()["already_resolved"])
        self.assertEqual(client.get(f"/tickets/{ticket_id}").json()["status"], "resolved")
        self.assertEqual(client.get("/metrics/tools").status_code, 200)
        self.assertEqual(client.get("/tool-calls", headers={"X-User-Role": "operator"}).status_code, 200)


if __name__ == "__main__":
    unittest.main()
