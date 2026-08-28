import unittest
from unittest.mock import patch

from fastapi.testclient import TestClient

from app.main import app
from app.models import AgentSummary, ChatResponse, TraceStep


class ApiContractTests(unittest.TestCase):
    def setUp(self) -> None:
        self.client = TestClient(app)

    def test_health_and_system_status(self) -> None:
        health = self.client.get("/health")
        status = self.client.get("/system/status")

        self.assertEqual(health.status_code, 200)
        # 健康检查 v1.0 起附带版本与运行时长（增量字段，status 语义不变）
        self.assertEqual(health.json()["status"], "ok")
        self.assertIn("version", health.json())
        self.assertIn("uptime_seconds", health.json())
        self.assertEqual(status.status_code, 200)
        self.assertIn("document_count", status.json())
        self.assertIn("embedding", status.json())

    def test_agentic_chat_contract(self) -> None:
        mocked_response = ChatResponse(
            answer="测试答案\n\n证据引用：\n- [来源 1] sample.md / chunk 0",
            sources=[],
            trace=[TraceStep(name="citation_check", status="repaired", detail="已补引用")],
            agent_summary=AgentSummary(
                workflow="agentic",
                intent="causal",
                complexity="simple",
                retrieval_rounds=1,
                queries=["延期原因"],
                evidence_status="passed",
                citation_status="repaired",
                agents=["Router Agent", "Reviewer Agent"],
            ),
        )

        with (
            patch("app.routes.chat.answer_agentic_question", return_value=mocked_response) as mocked,
            patch("app.routes.chat.safe_record_chat_metric") as metric_recorder,
        ):
            response = self.client.post(
                "/chat",
                json={
                    "question": "项目为什么延期？",
                    "answer_mode": "local",
                    "retriever_mode": "hybrid",
                    "workflow_mode": "agentic",
                },
            )

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["agent_summary"]["workflow"], "agentic")
        self.assertEqual(payload["trace"][-1]["name"], "citation_check")
        # 安全默认值：未携带 X-User-Role 的请求按 viewer（只读）处理，不再默认可写。
        mocked.assert_called_once_with(
            "项目为什么延期？",
            answer_mode="local",
            retriever_mode="hybrid",
            actor_role="viewer",
            actor_user="anonymous",
        )
        metric_recorder.assert_called_once()

    def test_standard_chat_keeps_backward_compatibility(self) -> None:
        mocked_response = ChatResponse(answer="标准回答", sources=[], trace=[])
        with (
            patch("app.routes.chat.answer_question", return_value=mocked_response) as mocked,
            patch("app.routes.chat.safe_record_chat_metric") as metric_recorder,
        ):
            response = self.client.post(
                "/chat",
                json={
                    "question": "项目状态",
                    "answer_mode": "local",
                    "retriever_mode": "keyword",
                    "workflow_mode": "standard",
                },
            )

        self.assertEqual(response.status_code, 200)
        self.assertIsNone(response.json()["agent_summary"])
        mocked.assert_called_once_with("项目状态", answer_mode="local", retriever_mode="keyword")
        metric_recorder.assert_called_once()

    def test_metrics_summary_contract(self) -> None:
        response = self.client.get("/metrics/summary")
        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertIn("total_requests", payload)
        self.assertIn("p95_latency_ms", payload)
        self.assertIn("citation_ready_rate", payload)


if __name__ == "__main__":
    unittest.main()
