import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from fastapi.testclient import TestClient

from app.database import get_chat_metrics_summary, record_chat_metric
from app.main import app
from app.models import Source
from app.rag import build_answer, build_local_usage, estimate_tokens, ingest_document


SAMPLE_TEXT = (
    "客户 B 的项目原计划在 2026 年 6 月 20 日交付。\n"
    "有人操作失误导致了项目交付时间推迟到 2026 年 7 月 8 日。\n"
    "延期原因：操作失误。\n"
    "项目负责人是李四。\n"
    "合同中约定，如果延期超过 18 天，需要向客户提交说明书。"
)


def build_source() -> Source:
    return Source(
        document_id="doc-1",
        filename="sample.md",
        chunk_index=0,
        score=12,
        content=SAMPLE_TEXT,
    )


class TokenUsageTests(unittest.TestCase):
    def test_estimate_tokens_scales_with_text(self) -> None:
        self.assertEqual(estimate_tokens(""), 0)
        self.assertGreater(estimate_tokens("客户项目延期原因分析"), 0)

    def test_local_answer_reports_usage_without_cost(self) -> None:
        answer, trace, usage = build_answer("项目为什么延期？", [build_source()], "local")
        self.assertTrue(answer)
        self.assertGreater(usage.total_tokens, 0)
        self.assertEqual(usage.estimated_cost_usd, 0.0)
        self.assertIn(usage.source, {"local_rule", "local_template"})
        self.assertEqual(usage.total_tokens, usage.prompt_tokens + usage.completion_tokens)

    def test_local_usage_builder_marks_source(self) -> None:
        usage = build_local_usage("问题", [], "答案内容", "local_template")
        self.assertEqual(usage.source, "local_template")
        self.assertGreater(usage.completion_tokens, 0)


class MetricsTokenTests(unittest.TestCase):
    def test_summary_aggregates_tokens_and_cost(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            with patch("app.database.DB_PATH", Path(temp_dir) / "metrics.sqlite3"):
                base = {
                    "workflow_mode": "agentic",
                    "answer_mode": "api",
                    "retriever_mode": "hybrid",
                    "intent": "causal",
                    "complexity": "simple",
                    "retrieval_rounds": 1,
                    "query_count": 4,
                    "evidence_status": "passed",
                    "citation_status": "repaired",
                    "source_count": 1,
                    "outcome": "answered",
                    "answer_status": "api",
                    "latency_ms": 900.0,
                    "answer_chars": 120,
                }
                record_chat_metric(
                    **base, prompt_tokens=1000, completion_tokens=500,
                    total_tokens=1500, estimated_cost_usd=0.00082,
                )
                record_chat_metric(
                    **{**base, "answer_mode": "local", "latency_ms": 8.0},
                    prompt_tokens=700, completion_tokens=300, total_tokens=1000,
                )
                summary = get_chat_metrics_summary()

        self.assertEqual(summary["total_tokens"], 2500)
        self.assertEqual(summary["avg_tokens_per_request"], 1250.0)
        self.assertAlmostEqual(summary["total_estimated_cost_usd"], 0.00082)
        self.assertEqual(summary["tokens_by_answer_mode"]["api"], 1500)
        self.assertEqual(summary["cost_by_answer_mode"]["local"], 0.0)


class ChatLogAndFeedbackTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.db_patcher = patch("app.database.DB_PATH", Path(self.temp_dir.name) / "v5.sqlite3")
        self.db_patcher.start()
        self.client = TestClient(app)
        ingest_document("sample.md", SAMPLE_TEXT)

    def tearDown(self) -> None:
        self.db_patcher.stop()
        self.temp_dir.cleanup()

    def ask(self, question: str) -> dict:
        response = self.client.post(
            "/chat",
            json={
                "question": question,
                "answer_mode": "local",
                "retriever_mode": "keyword",
                "workflow_mode": "agentic",
            },
        )
        self.assertEqual(response.status_code, 200)
        return response.json()

    def test_chat_writes_log_with_tokens_and_returns_log_id(self) -> None:
        payload = self.ask("客户B的项目为什么延期？")
        self.assertGreater(payload["log_id"], 0)
        self.assertIsNotNone(payload["token_usage"])
        self.assertGreater(payload["token_usage"]["total_tokens"], 0)

        logs = self.client.get("/chat-logs", headers={"X-User-Role": "operator"}).json()
        self.assertEqual(len(logs), 1)
        self.assertEqual(logs[0]["outcome"], "answered")
        self.assertGreater(logs[0]["total_tokens"], 0)

    def test_refused_chat_is_replayable_with_trace(self) -> None:
        payload = self.ask("火星基地的氧气供应方案是什么？")
        refused = self.client.get("/chat-logs", params={"outcome": "refused"}, headers={"X-User-Role": "operator"}).json()
        self.assertEqual(len(refused), 1)
        detail = self.client.get(f"/chat-logs/{payload['log_id']}", headers={"X-User-Role": "operator"}).json()
        self.assertTrue(detail["trace"])
        self.assertEqual(detail["outcome"], "refused")

    def test_feedback_updates_log_and_summary(self) -> None:
        first = self.ask("客户B的项目为什么延期？")
        second = self.ask("项目负责人是谁？")

        up = self.client.post(f"/chat-logs/{first['log_id']}/feedback", json={"rating": "up"})
        down = self.client.post(
            f"/chat-logs/{second['log_id']}/feedback",
            json={"rating": "down", "note": "答案不够具体"},
        )
        missing = self.client.post("/chat-logs/99999/feedback", json={"rating": "up"})

        self.assertEqual(up.status_code, 200)
        self.assertEqual(down.status_code, 200)
        self.assertEqual(missing.status_code, 404)

        summary = self.client.get("/metrics/summary").json()
        self.assertEqual(summary["feedback_count"], 2)
        self.assertEqual(summary["positive_feedback"], 1)
        self.assertEqual(summary["satisfaction_rate"], 0.5)

        detail = self.client.get(f"/chat-logs/{second['log_id']}", headers={"X-User-Role": "operator"}).json()
        self.assertEqual(detail["feedback"], -1)
        self.assertEqual(detail["feedback_note"], "答案不够具体")

    def test_graph_endpoints_contract(self) -> None:
        overview = self.client.get("/graph/overview")
        entities = self.client.get("/graph/entities", params={"entity_type": "customer"})
        paths = self.client.get("/graph/paths", params={"source": "客户B", "target": "李四"})
        rebuild = self.client.post("/graph/rebuild", headers={"X-User-Role": "operator"})
        rebuild_denied = self.client.post("/graph/rebuild", headers={"X-User-Role": "viewer"})

        self.assertEqual(overview.status_code, 200)
        self.assertGreaterEqual(overview.json()["entity_count"], 6)
        self.assertEqual(entities.json()[0]["name"], "客户B")
        self.assertTrue(paths.json()["paths"])
        self.assertEqual(rebuild.status_code, 200)
        self.assertEqual(rebuild_denied.status_code, 403)


if __name__ == "__main__":
    unittest.main()
