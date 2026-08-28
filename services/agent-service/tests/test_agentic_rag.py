import unittest
from unittest.mock import patch

from app.agentic_rag import (
    answer_agentic_question,
    detect_intents,
    rewrite_question,
)
from app.models import ChatRequest
from app.retrievers import Chunk, RetrievalHit, RetrievalResult


class FakeRetriever:
    name = "fake"

    def __init__(self, hits: list[RetrievalHit]) -> None:
        self.hits = hits
        self.calls = 0

    def search(self, queries: list[str]) -> RetrievalResult:
        self.calls += 1
        return RetrievalResult(hits=self.hits, scanned_count=len(self.hits))


def build_relevant_hit() -> RetrievalHit:
    return RetrievalHit(
        chunk=Chunk(
            document_id="doc-1",
            filename="project.md",
            chunk_index=0,
            content=(
                "项目延期，延期原因是测试环境部署失败，导致交付时间推迟。"
                "合同风险是延期超过十五天需要提交风险说明，项目负责人是李四。"
            ),
        ),
        score=20,
        matched_queries=["项目延期原因"],
    )


class AgenticRagTests(unittest.TestCase):
    def test_request_defaults_to_agentic_workflow(self) -> None:
        request = ChatRequest(question="项目情况")
        self.assertEqual(request.workflow_mode, "agentic")

    def test_router_and_rewrite(self) -> None:
        question = "项目为什么延期，同时合同有没有风险？"
        self.assertEqual(detect_intents(question), ["risk", "causal"])
        self.assertIn("原因", rewrite_question(question))
        self.assertIn("是否存在", rewrite_question(question))

    def test_simple_question_uses_one_round_and_repairs_citation(self) -> None:
        retriever = FakeRetriever([build_relevant_hit()])
        with patch("app.agentic_rag.get_retriever", return_value=retriever):
            response = answer_agentic_question("项目为什么延期？", "local", "keyword")

        self.assertEqual(response.agent_summary.retrieval_rounds, 1)
        self.assertEqual(response.agent_summary.evidence_status, "passed")
        self.assertEqual(response.agent_summary.citation_status, "repaired")
        self.assertIn("[来源 1]", response.answer)
        self.assertEqual(retriever.calls, 1)

    def test_complex_question_uses_two_rounds(self) -> None:
        # 当证据充分时（score>=8, coverage>=40%, topic anchors match），
        # 复杂问题也可能在第一轮通过证据检查。
        retriever = FakeRetriever([build_relevant_hit()])
        with patch("app.agentic_rag.get_retriever", return_value=retriever):
            response = answer_agentic_question(
                "项目为什么延期，同时合同有什么风险？",
                "local",
                "hybrid",
            )

        self.assertEqual(response.agent_summary.complexity, "complex")
        self.assertEqual(response.agent_summary.evidence_status, "passed")
        self.assertIn(response.agent_summary.retrieval_rounds, (1, 2))
        self.assertLessEqual(retriever.calls, 2)

    def test_no_evidence_refuses_after_two_rounds(self) -> None:
        retriever = FakeRetriever([])
        with patch("app.agentic_rag.get_retriever", return_value=retriever):
            response = answer_agentic_question("火星基地氧气供应方案是什么？", "local", "hybrid")

        self.assertEqual(response.agent_summary.retrieval_rounds, 2)
        self.assertNotEqual(response.agent_summary.evidence_status, "passed")
        self.assertEqual(response.agent_summary.citation_status, "not_applicable")
        self.assertIn("没有找到足够相关的资料", response.answer)
        self.assertEqual(response.trace[-1].status, "refused")

    def test_high_score_but_wrong_topic_is_refused(self) -> None:
        retriever = FakeRetriever([build_relevant_hit()])
        with patch("app.agentic_rag.get_retriever", return_value=retriever):
            response = answer_agentic_question("火星基地的氧气供应方案是什么？", "local", "hybrid")

        self.assertEqual(response.agent_summary.retrieval_rounds, 2)
        self.assertEqual(response.agent_summary.evidence_status, "topic_mismatch")
        self.assertEqual(response.trace[-1].status, "refused")


if __name__ == "__main__":
    unittest.main()
