import json
from pathlib import Path
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
        self.assertNotIn("cache", status.json()["embedding"])

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
            workspace_type="personal",
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

    def test_publication_deliverables_schema_is_versioned_and_machine_readable(self) -> None:
        contract = (
            Path(__file__).resolve().parents[3]
            / "contracts" / "http" / "publication-deliverables-v1.schema.json"
        )
        schema = json.loads(contract.read_text(encoding="utf-8"))

        self.assertTrue(schema["$id"].endswith("/publication-deliverables-v1.schema.json"))
        self.assertEqual(schema["type"], "object")
        self.assertEqual(
            set(schema["required"]),
            {"version", "knowledge_candidates", "action_items"},
        )
        self.assertEqual(schema["properties"]["version"]["$ref"], "#/$defs/version")

    def test_analysis_session_schema_requires_checkpoint_provenance(self) -> None:
        contract = (
            Path(__file__).resolve().parents[3]
            / "contracts" / "http" / "analysis-session-v1.schema.json"
        )
        schema = json.loads(contract.read_text(encoding="utf-8"))

        self.assertTrue(schema["$id"].endswith("/analysis-session-v1.schema.json"))
        self.assertTrue({
            "checkpoint_version", "evidence_revision", "evidence_snapshot_sha256",
            "retrieval_mode",
        }.issubset(schema["required"]))
        self.assertEqual(schema["properties"]["retrieval_mode"]["const"], "hybrid")
        self.assertEqual(schema["properties"]["stages"]["maxItems"], 6)

    def test_workspace_collaboration_schema_is_versioned_and_machine_readable(self) -> None:
        contract = (
            Path(__file__).resolve().parents[3]
            / "contracts" / "http" / "workspace-collaboration-v1.schema.json"
        )
        schema = json.loads(contract.read_text(encoding="utf-8"))

        self.assertTrue(schema["$id"].endswith("/workspace-collaboration-v1.schema.json"))
        self.assertEqual(schema["type"], "object")
        self.assertEqual(
            set(schema["$defs"]["workspaceRole"]["enum"]),
            {"OWNER", "ADMIN", "MEMBER", "VIEWER"},
        )
        self.assertIn("invitation", schema["$defs"])
        self.assertIn("activeSession", schema["$defs"])

    def test_cache_observability_schema_matches_status_response(self) -> None:
        contract = (
            Path(__file__).resolve().parents[3]
            / "contracts" / "http" / "cache-observability-v1.schema.json"
        )
        schema = json.loads(contract.read_text(encoding="utf-8"))
        self.assertTrue(schema["$id"].endswith("/cache-observability-v1.schema.json"))
        self.assertIn("cache", schema["required"])
        self.assertEqual(
            set(schema["$defs"]["cacheMetric"]["required"]),
            {"entries", "max_entries", "hits", "misses", "requests", "hit_rate"},
        )

        response = self.client.get("/embeddings/status")
        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["cache"]["scope"], "process")
        for cache_name in ("embedding_vectors", "chunk_snapshots"):
            self.assertEqual(
                set(payload["cache"][cache_name]),
                {"entries", "max_entries", "hits", "misses", "requests", "hit_rate"},
            )

    def test_approved_knowledge_contract_requires_materialization_provenance(self) -> None:
        contract = (
            Path(__file__).resolve().parents[3]
            / "contracts" / "http" / "approved-knowledge-v1.schema.json"
        )
        schema = json.loads(contract.read_text(encoding="utf-8"))
        self.assertTrue(schema["$id"].endswith("/approved-knowledge-v1.schema.json"))
        self.assertTrue({
            "knowledge_document_id", "knowledge_content_sha256", "knowledge_published_at",
        }.issubset(schema["required"]))
        self.assertEqual(
            schema["allOf"][0]["if"]["properties"]["status"]["const"], "APPROVED",
        )

    def test_knowledge_lifecycle_contract_defines_version_chain_and_governance(self) -> None:
        contract = (
            Path(__file__).resolve().parents[3]
            / "contracts" / "http" / "knowledge-lifecycle-v1.schema.json"
        )
        schema = json.loads(contract.read_text(encoding="utf-8"))

        self.assertTrue(schema["$id"].endswith("/knowledge-lifecycle-v1.schema.json"))
        self.assertEqual(
            set(schema["$defs"]["knowledgeVersion"]["properties"]["status"]["enum"]),
            {"ACTIVE", "SUPERSEDED", "REVOKED"},
        )
        self.assertEqual(
            set(schema["$defs"]["lifecycleRequest"]["properties"]["action"]["enum"]),
            {"REVOKE", "SUPERSEDE"},
        )


if __name__ == "__main__":
    unittest.main()
