import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from app.database import connect, get_chat_metrics_summary, record_chat_metric
from app.routes.chat import infer_standard_outcome
from app.models import ChatResponse


def record_sample(**overrides: object) -> None:
    values: dict[str, object] = {
        "workflow_mode": "agentic",
        "answer_mode": "local",
        "retriever_mode": "hybrid",
        "intent": "causal",
        "complexity": "simple",
        "retrieval_rounds": 1,
        "query_count": 4,
        "evidence_status": "passed",
        "citation_status": "repaired",
        "source_count": 1,
        "outcome": "answered",
        "answer_status": "rule_matched",
        "latency_ms": 10.0,
        "answer_chars": 120,
    }
    values.update(overrides)
    record_chat_metric(**values)


class ChatMetricsTests(unittest.TestCase):
    def test_standard_empty_knowledge_base_is_counted_as_refusal(self) -> None:
        response = ChatResponse(answer="当前知识库中还没有可用资料。请先上传文档。", sources=[])
        self.assertEqual(infer_standard_outcome(response), "refused")

    def test_summary_rates_latency_and_privacy(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            db_path = Path(temp_dir) / "metrics.sqlite3"
            with patch("app.database.DB_PATH", db_path):
                record_sample()
                record_sample(
                    intent="general",
                    complexity="simple",
                    retrieval_rounds=2,
                    query_count=3,
                    evidence_status="topic_mismatch",
                    citation_status="not_applicable",
                    source_count=1,
                    outcome="refused",
                    answer_status="not_generated",
                    latency_ms=30.0,
                )
                record_sample(
                    workflow_mode="standard",
                    intent="standard",
                    complexity="standard",
                    evidence_status="error",
                    citation_status="not_applicable",
                    source_count=0,
                    outcome="error",
                    answer_status="error",
                    latency_ms=100.0,
                )
                summary = get_chat_metrics_summary()
                with connect() as conn:
                    columns = [row["name"] for row in conn.execute("pragma table_info(chat_metrics)").fetchall()]

        self.assertEqual(summary["total_requests"], 3)
        self.assertAlmostEqual(summary["answer_rate"], 1 / 3)
        self.assertAlmostEqual(summary["refusal_rate"], 1 / 3)
        self.assertAlmostEqual(summary["error_rate"], 1 / 3)
        self.assertEqual(summary["citation_ready_rate"], 1.0)
        self.assertEqual(summary["p95_latency_ms"], 100.0)
        self.assertEqual(summary["avg_retrieval_rounds"], 1.33)
        self.assertEqual(summary["intent_usage"]["causal"], 1)
        self.assertEqual(summary["answer_mode_usage"]["local"], 3)
        self.assertEqual(summary["avg_latency_by_workflow"]["agentic"], 20.0)
        self.assertNotIn("question", columns)


if __name__ == "__main__":
    unittest.main()
