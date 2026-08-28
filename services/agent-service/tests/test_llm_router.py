"""B1/B2/B3 回归测试：LLM 路由/规划/工具选择（规则降级）+ 声明级溯源。

全部用例用 mock 模拟 LLM，不依赖真实 API Key；无 Key 环境必须走规则降级。
"""
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from app.agentic_rag import answer_agentic_question
from app.citation_review import find_unsupported_claims, review_citations
from app.llm_router import (
    LLMJsonResult,
    RouterDecision,
    llm_plan_queries,
    llm_route_question,
    llm_select_tool_calls,
)
from app.models import Source
from tests.test_agentic_rag import FakeRetriever, build_relevant_hit


class LlmRouterUnitTests(unittest.TestCase):
    def test_route_question_parses_decision(self) -> None:
        with patch(
            "app.llm_router._chat_json",
            return_value=LLMJsonResult(
                data={"intent": "risk", "complexity": "complex"},
                prompt_tokens=10,
                completion_tokens=5,
            ),
        ):
            decision = llm_route_question("合同有什么风险？")
        self.assertIsNotNone(decision)
        assert decision is not None
        self.assertEqual(decision.intent, "risk")
        self.assertEqual(decision.complexity, "complex")
        self.assertEqual(decision.total_tokens, 15)

    def test_route_question_falls_back_without_key(self) -> None:
        with patch("app.llm_router.is_llm_configured", return_value=False):
            self.assertIsNone(llm_route_question("合同有什么风险？"))

    def test_plan_queries_parses_list(self) -> None:
        with patch(
            "app.llm_router._chat_json",
            return_value=LLMJsonResult(data=["客户A项目延期", "部署失败原因"], prompt_tokens=4, completion_tokens=4),
        ):
            result = llm_plan_queries("客户A项目为什么延期？", "causal")
        self.assertIsNotNone(result)
        assert result is not None
        self.assertEqual(result.data, ["客户A项目延期", "部署失败原因"])

    def test_plan_queries_rejects_non_list(self) -> None:
        with patch("app.llm_router._chat_json", return_value=LLMJsonResult(data={"bad": 1})):
            self.assertIsNone(llm_plan_queries("问题", "general"))

    def test_select_tool_calls_parses_list(self) -> None:
        with patch(
            "app.llm_router._chat_json",
            return_value=LLMJsonResult(data=[{"tool": "query_tickets", "arguments": {"status": "open"}}]),
        ):
            result = llm_select_tool_calls("查一下打开的工单")
        self.assertIsNotNone(result)
        assert result is not None
        self.assertEqual(result.data, [("query_tickets", {"status": "open"})])

    def test_select_tool_calls_returns_empty_list_as_no_tools(self) -> None:
        with patch("app.llm_router._chat_json", return_value=LLMJsonResult(data=[])):
            result = llm_select_tool_calls("客户A的项目为什么延期？")
        self.assertIsNotNone(result)
        assert result is not None
        self.assertEqual(result.data, [])


class AgenticLlmIntegrationTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.db_patcher = patch("app.database.DB_PATH", Path(self.temp_dir.name) / "llm.sqlite3")
        self.db_patcher.start()

    def tearDown(self) -> None:
        self.db_patcher.stop()
        self.temp_dir.cleanup()

    def test_router_uses_llm_when_available(self) -> None:
        with (
            patch(
                "app.agentic_rag.llm_route_question",
                return_value=RouterDecision(intent="risk", complexity="complex", prompt_tokens=10, completion_tokens=5),
            ),
            patch("app.agentic_rag.get_retriever", return_value=FakeRetriever([build_relevant_hit()])),
        ):
            response = answer_agentic_question("项目为什么延期？", "local", "keyword")
        self.assertEqual(response.agent_summary.intent, "risk")
        self.assertEqual(response.agent_summary.complexity, "complex")
        self.assertTrue(any("LLM 路由" in step.detail for step in response.trace))
        self.assertIsNotNone(response.token_usage)
        assert response.token_usage is not None
        self.assertGreaterEqual(response.token_usage.prompt_tokens, 10)

    def test_planner_uses_llm_queries_when_available(self) -> None:
        with (
            patch(
                "app.agentic_rag.llm_plan_queries",
                return_value=LLMJsonResult(data=["客户A项目延期", "部署失败原因"], prompt_tokens=4, completion_tokens=4),
            ),
            patch("app.agentic_rag.get_retriever", return_value=FakeRetriever([build_relevant_hit()])),
        ):
            response = answer_agentic_question("项目为什么延期？", "local", "keyword")
        self.assertIn("部署失败原因", response.agent_summary.queries)
        self.assertTrue(any("LLM 规划" in step.detail for step in response.trace))

    def test_tool_agent_uses_llm_selection_when_available(self) -> None:
        with patch(
            "app.agentic_rag.llm_select_tool_calls",
            return_value=LLMJsonResult(data=[("query_tickets", {})], prompt_tokens=6, completion_tokens=3),
        ):
            response = answer_agentic_question("查一下现有工单", "local", "keyword")
        tool_calls = response.agent_summary.tool_calls
        self.assertTrue(tool_calls)
        self.assertEqual(tool_calls[0].tool_name, "query_tickets")
        self.assertEqual(tool_calls[0].status, "succeeded")
        self.assertTrue(any("LLM 工具选择" in step.detail for step in response.trace))

    def test_router_tokens_recorded_even_on_refusal(self) -> None:
        with (
            patch(
                "app.agentic_rag.llm_route_question",
                return_value=RouterDecision(intent="general", complexity="simple", prompt_tokens=7, completion_tokens=2),
            ),
            patch("app.agentic_rag.get_retriever", return_value=FakeRetriever([])),
        ):
            response = answer_agentic_question("火星基地的氧气供应方案是什么？", "local", "hybrid")
        self.assertIsNotNone(response.token_usage)
        assert response.token_usage is not None
        self.assertEqual(response.token_usage.prompt_tokens, 7)
        self.assertEqual(response.token_usage.source, "router")


class ClaimGroundingTests(unittest.TestCase):
    def _sources(self) -> list[Source]:
        return [
            Source(
                document_id="d1",
                filename="a.md",
                chunk_index=0,
                score=10,
                title="项目记录",
                content="项目负责人是李四。调整后交付日期：2026年7月8日。",
            )
        ]

    def test_unanchored_date_claim_is_flagged(self) -> None:
        claims = find_unsupported_claims("项目将于2026年9月9日交付。负责人是李四。", self._sources())
        self.assertTrue(claims)
        self.assertIn("2026年9月9日", claims[0])

    def test_anchored_claims_pass(self) -> None:
        claims = find_unsupported_claims("调整后交付日期是2026年7月8日。", self._sources())
        self.assertEqual(claims, [])

    def test_review_appends_warning_for_unsupported_claims(self) -> None:
        answer = "答案 [来源 1]\n项目将于2026年9月9日交付。"
        reviewed, status, detail = review_citations(answer, self._sources())
        self.assertEqual(status, "passed")
        self.assertIn("⚠️", reviewed)
        self.assertIn("找不到数字锚点", detail)


if __name__ == "__main__":
    unittest.main()
