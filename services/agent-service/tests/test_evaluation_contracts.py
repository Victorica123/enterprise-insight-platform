"""Quality gates must measure the advertised retrieval window and decision path."""

import importlib.util
import unittest
from pathlib import Path
from types import SimpleNamespace

EVALUATOR = Path(__file__).resolve().parents[3] / "quality/agent-evals/evaluate_v6.py"
spec = importlib.util.spec_from_file_location("evaluate_v6", EVALUATOR)
evaluate_v6 = importlib.util.module_from_spec(spec)
spec.loader.exec_module(evaluate_v6)


class EvaluationContractTests(unittest.TestCase):
    def test_fourth_source_is_not_a_recall_at_three_hit(self):
        case = {"id": "rank-window", "should_answer": True, "expected_docs": ["wanted.md"], "expected_facts": ["fact"]}
        response = SimpleNamespace(
            agent_summary=SimpleNamespace(evidence_status="passed"), answer="fact",
            sources=[SimpleNamespace(filename=name) for name in ("a.md", "b.md", "c.md", "wanted.md")],
        )
        self.assertFalse(evaluate_v6.judge_case(case, response)["retrieval_ok"])
        response.sources = response.sources[1:]
        self.assertTrue(evaluate_v6.judge_case(case, response)["retrieval_ok"])

    def test_good_keyword_decisions_cannot_hide_bad_hybrid_decisions(self):
        summary = {
            "keyword": {"decision_accuracy": 1.0},
            "hybrid": {"decision_accuracy": 0.5, "recall3": 1.0, "fact_coverage": 1.0, "p95_latency_ms": 1},
        }
        self.assertFalse(evaluate_v6.passes_quality_gates(summary))
        summary["hybrid"]["decision_accuracy"] = 1.0
        self.assertTrue(evaluate_v6.passes_quality_gates(summary))
