"""阶段 0.4 / 0.5 / 0.7 / 0.8 回归：调用上限、证据字符预算、提示词外置、影子路由。

全部用例不依赖真实 API Key；模型调用用 fake client 或 mock，预算门必须降级而不是报错。
"""

from __future__ import annotations

import json
import os
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from app.agentic_rag import answer_agentic_question
from app.architecture.context import RequestContext, request_call_limits
from app.architecture.orchestration import (
    STANDARD_SKIPPED_STEPS,
    ConversationInput,
    ConversationOrchestrator,
    build_default_chain,
)
from app.architecture.planning import shadow_decision
from app.call_limits import (
    CallLimitExceeded,
    LimitCounter,
    acquire_call,
    current_call_limits,
    try_acquire_call,
)
from app.chat_observability_store import get_chat_metrics_summary, record_chat_metric
from app.config import CallLimits, EvidenceBudgetSettings, get_call_limits
from app.database import connect, init_db
from app.evidence_budget import ELLIPSIS, MIN_TAIL_CHARS, apply_evidence_budget, trim_content
from app.llm import build_system_prompt, build_user_prompt
from app.llm_client import create_chat_completion
from app.llm_router import llm_route_question
from app.main import app
from app.models import ChatResponse, Source
from app.prompts import (
    PROMPT_CATALOG,
    clear_prompt_cache,
    list_packaged_prompts,
    load_prompt,
    prompt_placeholders,
    render_prompt,
)
from app.rag import ingest_document
from app.retrievers import Chunk, RetrievalHit
from app.ticket_store import create_ticket
from app.tool_observability_store import list_tool_call_logs
from app.tools import execute_tool
from fastapi.testclient import TestClient

from tests.test_agentic_rag import FakeRetriever

RELEVANT_TEXT = (
    "项目延期，延期原因是测试环境部署失败，导致交付时间推迟。"
    "合同风险是延期超过十五天需要提交风险说明，项目负责人是李四。"
)


def make_source(content: str, index: int = 0, score: int = 10) -> Source:
    return Source(
        document_id="doc-1",
        filename="project.md",
        chunk_index=index,
        score=score,
        content=content,
    )


def fake_completion(content: str = '{"intent": "risk", "complexity": "simple"}') -> SimpleNamespace:
    message = SimpleNamespace(content=content)
    usage = SimpleNamespace(prompt_tokens=3, completion_tokens=2)
    return SimpleNamespace(choices=[SimpleNamespace(message=message)], usage=usage)


class FakeChatClient:
    def __init__(self, content: str) -> None:
        self.calls = 0
        self._content = content
        self.chat = SimpleNamespace(completions=SimpleNamespace(create=self._create))

    def _create(self, **kwargs: object) -> SimpleNamespace:
        self.calls += 1
        return fake_completion(self._content)


LLM_ENV = {
    "LLM_PROVIDER": "openai",
    "OPENAI_API_KEY": "sk-test",
    "LLM_ROUTER_ENABLED": "1",
    "LLM_RESPONSE_FORMAT": "auto",
}


class LimitCounterTests(unittest.TestCase):
    def test_counter_counts_and_records_denials(self) -> None:
        counter = LimitCounter(CallLimits(max_model_calls=2, max_tool_calls=1))

        self.assertTrue(counter.try_acquire("model", label="router"))
        self.assertTrue(counter.try_acquire("model", label="answer"))
        self.assertFalse(counter.try_acquire("model", label="planner"))
        self.assertTrue(counter.try_acquire("tool", label="query_tickets"))
        self.assertFalse(counter.try_acquire("tool", label="query_tickets"))

        self.assertEqual(counter.model_calls, 2)
        self.assertEqual(counter.tool_calls, 1)
        self.assertEqual(counter.remaining("model"), 0)
        self.assertEqual(counter.denied_model_calls, 1)
        self.assertEqual(counter.denied_tool_calls, 1)
        self.assertTrue(counter.exceeded)
        step = counter.trace_step()
        self.assertEqual(step.name, "call_limits")
        self.assertEqual(step.status, "degraded")
        self.assertIn("planner", step.detail)
        self.assertIn("2/2", step.detail)

    def test_fresh_counter_is_not_attempted_and_acquire_raises_when_spent(self) -> None:
        counter = LimitCounter(CallLimits(max_model_calls=1, max_tool_calls=1))
        self.assertFalse(counter.attempted)
        self.assertEqual(counter.trace_step().status, "ok")

        counter.acquire("model", label="answer")
        with self.assertRaises(CallLimitExceeded) as raised:
            counter.acquire("model", label="answer")
        self.assertEqual(raised.exception.kind, "model")
        self.assertEqual(raised.exception.limit, 1)
        self.assertTrue(counter.attempted)

    def test_module_gates_are_no_ops_outside_a_bound_request(self) -> None:
        self.assertIsNone(current_call_limits())
        acquire_call("model", label="unbound")  # must not raise
        self.assertTrue(try_acquire_call("tool", label="unbound"))

        with request_call_limits(limits=CallLimits(max_model_calls=1, max_tool_calls=1)) as counter:
            self.assertIs(current_call_limits(), counter)
            acquire_call("model", label="first")
            with self.assertRaises(CallLimitExceeded):
                acquire_call("model", label="second")
            self.assertTrue(try_acquire_call("tool", label="first"))
            self.assertFalse(try_acquire_call("tool", label="second"))
        self.assertIsNone(current_call_limits())

    def test_defaults_match_plan_and_env_override(self) -> None:
        with patch.dict(os.environ, {"AGENT_MAX_MODEL_CALLS": "", "AGENT_MAX_TOOL_CALLS": ""}):
            defaults = get_call_limits()
        self.assertEqual((defaults.max_model_calls, defaults.max_tool_calls), (8, 6))
        with patch.dict(os.environ, {"AGENT_MAX_MODEL_CALLS": "3", "AGENT_MAX_TOOL_CALLS": "0"}):
            custom = get_call_limits()
        self.assertEqual((custom.max_model_calls, custom.max_tool_calls), (3, 1))

    def test_request_context_facade_exposes_budget(self) -> None:
        self.assertTrue(hasattr(RequestContext, "from_principal"))
        self.assertIs(request_call_limits, __import__("app.call_limits", fromlist=["x"]).request_call_limits)


class ModelCallBudgetTests(unittest.TestCase):
    def test_chat_completion_consumes_budget_and_stops_before_egress(self) -> None:
        client = FakeChatClient('{"ok": true}')
        limits = CallLimits(max_model_calls=1, max_tool_calls=6)
        with (
            patch.dict(os.environ, LLM_ENV),
            patch("app.llm_client._build_client", return_value=client),
            patch("app.llm_client.require_model_egress_allowed"),
            request_call_limits(limits=limits) as counter,
        ):
            create_chat_completion(messages=[{"role": "user", "content": "x"}], temperature=0.1, purpose="a")
            with self.assertRaises(CallLimitExceeded):
                create_chat_completion(
                    messages=[{"role": "user", "content": "y"}], temperature=0.1, purpose="b"
                )

        self.assertEqual(client.calls, 1)
        self.assertEqual(counter.model_calls, 1)
        self.assertEqual(counter.denials, ["model:b"])

    def test_router_falls_back_to_rules_when_budget_is_spent(self) -> None:
        client = FakeChatClient('{"intent": "risk", "complexity": "complex"}')
        limits = CallLimits(max_model_calls=1, max_tool_calls=6)
        with (
            patch.dict(os.environ, LLM_ENV),
            patch("app.llm_client._build_client", return_value=client),
            patch("app.llm_client.require_model_egress_allowed"),
            request_call_limits(limits=limits) as counter,
        ):
            first = llm_route_question("合同有什么风险？")
            second = llm_route_question("合同有什么风险？")

        self.assertIsNotNone(first)
        assert first is not None
        self.assertEqual(first.intent, "risk")
        self.assertIsNone(second)
        self.assertEqual(client.calls, 1)
        self.assertEqual(counter.denied_model_calls, 1)

    def test_agentic_answer_degrades_to_template_when_answer_budget_is_spent(self) -> None:
        retriever = FakeRetriever(
            [RetrievalHit(chunk=Chunk("doc-1", "project.md", 0, RELEVANT_TEXT), score=20, matched_queries=["延期"])]
        )
        client = FakeChatClient('{"intent": "fact", "complexity": "simple"}')
        orchestrator = ConversationOrchestrator(call_limits=CallLimits(max_model_calls=1, max_tool_calls=6))
        with (
            patch.dict(os.environ, {**LLM_ENV, "LLM_ROUTER_ENABLED": "1"}),
            patch("app.llm_client._build_client", return_value=client),
            patch("app.llm_client.require_model_egress_allowed"),
            patch("app.agentic_rag.get_retriever", return_value=retriever),
        ):
            response, plan = orchestrator.run(
                ConversationInput(
                    question="项目负责人是谁？",
                    workflow_mode="agentic",
                    answer_mode="api",
                    retriever_mode="keyword",
                )
            )

        # 路由用掉唯一一次模型预算；规划与回答只能走规则 / 模板，且答案照常返回
        self.assertEqual(plan.mode, "agentic")
        self.assertEqual(client.calls, 1)
        self.assertTrue(response.answer)
        self.assertEqual(response.trace[-1].name, "call_limits")
        self.assertEqual(response.trace[-1].status, "degraded")
        statuses = {step.name: step.status for step in response.trace}
        self.assertEqual(statuses["answer"], "call_limited")
        assert response.token_usage is not None
        self.assertEqual(response.token_usage.source, "local_template")


class ToolCallBudgetTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.db_patcher = patch("app.database.DB_PATH", Path(self.temp_dir.name) / "budget.sqlite3")
        self.db_patcher.start()

    def tearDown(self) -> None:
        self.db_patcher.stop()
        self.temp_dir.cleanup()

    def test_tool_calls_beyond_budget_are_skipped_and_audited(self) -> None:
        create_ticket("预算示例", "工具预算测试", status="open")
        with request_call_limits(limits=CallLimits(max_model_calls=8, max_tool_calls=1)) as counter:
            first = execute_tool("query_tickets", {}, actor_role="operator")
            second = execute_tool("query_tickets", {}, actor_role="operator")

        self.assertTrue(first.success)
        self.assertFalse(second.success)
        self.assertEqual(second.status, "limited")
        self.assertIn("上限", second.result["error"])
        self.assertEqual(counter.tool_calls, 1)
        self.assertEqual(counter.denials, ["tool:query_tickets"])

        statuses = [row["status"] for row in list_tool_call_logs()]
        self.assertEqual(statuses.count("limited"), 1)
        self.assertEqual(statuses.count("succeeded"), 1)

    def test_tool_calls_are_unlimited_outside_a_request(self) -> None:
        for _ in range(3):
            self.assertTrue(execute_tool("query_tickets", {}, actor_role="operator").success)


class EvidenceBudgetTests(unittest.TestCase):
    def test_trim_prefers_sentence_boundary_and_marks_ellipsis(self) -> None:
        # 句号落在配额 60% 之后：回退到句末，补省略号
        text = "甲" * 20 + "。" + "乙" * 50
        trimmed = trim_content(text, 30)
        self.assertEqual(trimmed, "甲" * 20 + "。" + ELLIPSIS)
        self.assertLessEqual(len(trimmed), 30)
        self.assertEqual(trim_content("短文本", 30), "短文本")

        # 句号太靠前（30% 处）时硬截到配额，不为了句号丢掉大半配额
        early_boundary = "第一句话。第二句话。第三句话很长" + "很长" * 40 + "。"
        cut = trim_content(early_boundary, 30)
        self.assertEqual(len(cut), 30)
        self.assertTrue(cut.endswith(ELLIPSIS))
        self.assertTrue(cut.startswith("第一句话。第二句话。第三句话"))

    def test_budget_keeps_order_trims_per_source_and_drops_tail(self) -> None:
        budget = EvidenceBudgetSettings(per_source_chars=200, total_chars=450)
        sources = [
            make_source("A" * 300, index=0, score=30),
            make_source("B" * 100, index=1, score=20),
            make_source("C" * 300, index=2, score=10),
            make_source("D" * 50, index=3, score=5),
        ]
        result = apply_evidence_budget(sources, budget)

        self.assertEqual([source.chunk_index for source in result.sources], [0, 1, 2])
        self.assertEqual(len(result.sources[0].content), 200)
        self.assertTrue(result.sources[0].content.endswith(ELLIPSIS))
        self.assertEqual(result.sources[1].content, "B" * 100)
        # 剩余 150 >= MIN_TAIL_CHARS：第三个来源裁到剩余预算；第四个来源预算不足被丢弃
        self.assertEqual(len(result.sources[2].content), 150)
        self.assertLessEqual(result.budgeted_chars, budget.total_chars)
        self.assertEqual(result.original_chars, 750)
        self.assertEqual(len(result.trimmed), 2)
        self.assertEqual(result.dropped, ("project.md#chunk3",))
        self.assertTrue(result.changed)
        self.assertEqual(result.trace_step().status, "trimmed")
        self.assertIn("丢弃 1 个", result.trace_step().detail)
        # 原对象不被修改
        self.assertEqual(len(sources[0].content), 300)

    def test_budget_is_a_no_op_within_limits(self) -> None:
        budget = EvidenceBudgetSettings(per_source_chars=2200, total_chars=5200)
        sources = [make_source(RELEVANT_TEXT, index=i) for i in range(4)]
        result = apply_evidence_budget(sources, budget)
        self.assertEqual(result.sources, sources)
        self.assertFalse(result.changed)
        self.assertEqual(result.trace_step("evidence_budget_1").name, "evidence_budget_1")
        self.assertEqual(result.trace_step().status, "ok")
        self.assertGreater(MIN_TAIL_CHARS, 0)

    def test_agentic_sources_are_budgeted_before_answering(self) -> None:
        long_content = RELEVANT_TEXT + "补充说明。" * 200
        retriever = FakeRetriever(
            [RetrievalHit(chunk=Chunk("doc-1", "project.md", 0, long_content), score=20, matched_queries=["延期"])]
        )
        with (
            patch.dict(os.environ, {"EVIDENCE_SOURCE_CHAR_BUDGET": "300", "EVIDENCE_TOTAL_CHAR_BUDGET": "600"}),
            patch("app.agentic_rag.get_retriever", return_value=retriever),
        ):
            response = answer_agentic_question("项目为什么延期？", "local", "keyword")

        self.assertEqual(response.agent_summary.evidence_status, "passed")
        self.assertEqual(len(response.sources), 1)
        self.assertLessEqual(len(response.sources[0].content), 300)
        self.assertTrue(response.sources[0].content.endswith(ELLIPSIS))
        budget_steps = [step for step in response.trace if step.name.startswith("evidence_budget")]
        self.assertEqual([step.status for step in budget_steps], ["trimmed"])
        self.assertIsNotNone(budget_steps[0].duration_ms)

    def test_standard_path_records_budget_step(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            with patch("app.database.DB_PATH", Path(temp_dir) / "budget.sqlite3"):
                ingest_document("project.md", RELEVANT_TEXT)
                client = TestClient(app)
                payload = client.post(
                    "/chat",
                    json={
                        "question": "项目负责人是谁？",
                        "answer_mode": "local",
                        "retriever_mode": "keyword",
                        "workflow_mode": "standard",
                    },
                ).json()
        names = [step["name"] for step in payload["trace"]]
        self.assertIn("evidence_budget", names)
        budget_step = next(step for step in payload["trace"] if step["name"] == "evidence_budget")
        self.assertEqual(budget_step["status"], "ok")
        self.assertIn("未裁剪", budget_step["detail"])


class PromptTemplateTests(unittest.TestCase):
    def tearDown(self) -> None:
        clear_prompt_cache()

    def test_packaged_templates_match_catalog(self) -> None:
        self.assertEqual(sorted(PROMPT_CATALOG), list_packaged_prompts())
        for name, expected in PROMPT_CATALOG.items():
            self.assertEqual(prompt_placeholders(name), expected, name)

    def test_prompt_builders_only_fill_variables(self) -> None:
        self.assertEqual(build_system_prompt(), load_prompt("answer_system"))
        self.assertIn("只基于用户提供的来源资料回答", build_system_prompt())

        video = Source(
            source_type="video",
            document_id="doc-2",
            filename="meeting.mp4",
            chunk_index=3,
            score=8,
            content="会议决定推迟上线。",
            asset_id="asset-1",
            segment_id="seg-9",
            start_ms=1000,
            end_ms=4000,
        )
        prompt = build_user_prompt("为什么推迟？", [make_source(RELEVANT_TEXT), video], ["图谱：客户A -> 李四"])
        self.assertIn("用户问题：为什么推迟？", prompt)
        self.assertIn("来源 1\n来源类型：document", prompt)
        self.assertIn("来源 2\n来源类型：video", prompt)
        self.assertIn("资产 ID：asset-1\n片段 ID：seg-9\n", prompt)
        self.assertIn("系统补充上下文", prompt)
        self.assertIn("图谱：客户A -> 李四", prompt)
        self.assertTrue(prompt.endswith("说明依据来自哪些来源。"))
        self.assertNotIn("${", prompt)

        without_context = build_user_prompt("问题", [make_source("内容")])
        self.assertNotIn("系统补充上下文", without_context)

    def test_missing_placeholder_and_override_dir(self) -> None:
        with self.assertRaises(KeyError):
            render_prompt("router_user")
        self.assertIn("${question}", load_prompt("router_user"))

        with tempfile.TemporaryDirectory() as temp_dir:
            (Path(temp_dir) / "router_user.txt").write_text("覆盖：${question}\n", encoding="utf-8")
            with patch.dict(os.environ, {"AGENT_PROMPT_DIR": temp_dir}):
                clear_prompt_cache()
                self.assertEqual(render_prompt("router_user", question="Q"), "覆盖：Q")
                # 未覆盖的模板仍用包内默认
                self.assertIn("路由器", load_prompt("router_system"))
        clear_prompt_cache()
        self.assertEqual(render_prompt("router_user", question="Q"), "用户问题：Q")


class ShadowRoutingTests(unittest.TestCase):
    def test_shadow_decision_rules(self) -> None:
        self.assertEqual(shadow_decision("为什么？"), ("clarify", "no_content_anchor"))
        self.assertEqual(shadow_decision("查询工单 T-1 的状态"), ("tool_only", "direct_ticket_operation"))
        self.assertEqual(shadow_decision("项目负责人是谁？"), ("retrieval", "simple_lookup"))
        self.assertEqual(shadow_decision("客户A的项目为什么延期？"), ("agentic", "reasoning_intent"))
        self.assertEqual(
            shadow_decision("项目为什么延期，同时合同有什么风险？"), ("agentic", "complex_question")
        )
        self.assertEqual(shadow_decision("根据资料帮我创建工单"), ("agentic", "tool_assisted"))
        # 链上已有分类结果时直接复用，不再跑规则路由
        self.assertEqual(
            shadow_decision("项目负责人是谁？", intent="fact", complexity="complex"),
            ("agentic", "complex_question"),
        )

    def test_plan_carries_shadow_mode_and_agreement(self) -> None:
        chain = build_default_chain()
        standard = chain.run("客户A的项目为什么延期？", "standard", skip=STANDARD_SKIPPED_STEPS)
        self.assertEqual(standard.mode, "retrieval")
        self.assertEqual(standard.shadow_mode, "agentic")
        self.assertFalse(standard.mode_agreement)

        agentic = chain.run("客户A的项目为什么延期？", "agentic")
        self.assertEqual(agentic.mode, "agentic")
        self.assertEqual(agentic.shadow_mode, "agentic")
        self.assertTrue(agentic.mode_agreement)

        payload = json.loads(agentic.to_json())
        self.assertEqual(payload["shadow_mode"], "agentic")
        self.assertEqual(payload["shadow_reason"], "reasoning_intent")
        self.assertTrue(payload["mode_agreement"])
        decision = next(step for step in agentic.trace if step.name == "mode_decision")
        self.assertIn("影子路由", decision.detail)

    def test_orchestrator_run_returns_plan_and_skips_budget_step_when_unused(self) -> None:
        orchestrator = ConversationOrchestrator(
            standard_handler=lambda *a, **k: ChatResponse(answer="ok", sources=[]),
            agentic_handler=lambda *a, **k: ChatResponse(answer="ok", sources=[]),
        )
        response, plan = orchestrator.run(
            ConversationInput(
                question="项目负责人是谁？",
                workflow_mode="standard",
                answer_mode="local",
                retriever_mode="keyword",
            )
        )
        self.assertEqual(plan.mode, "retrieval")
        self.assertEqual(plan.shadow_mode, "retrieval")
        self.assertTrue(plan.mode_agreement)
        self.assertEqual(response.trace[0].name, "mode_decision")
        self.assertNotIn("call_limits", [step.name for step in response.trace])

    def test_metrics_summary_reports_agreement_rate(self) -> None:
        base = {
            "workflow_mode": "standard",
            "answer_mode": "local",
            "retriever_mode": "hybrid",
            "intent": "standard",
            "complexity": "standard",
            "retrieval_rounds": 1,
            "query_count": 1,
            "evidence_status": "passed",
            "citation_status": "not_applicable",
            "source_count": 1,
            "outcome": "answered",
            "answer_status": "local",
            "latency_ms": 5.0,
            "answer_chars": 50,
        }
        with tempfile.TemporaryDirectory() as temp_dir:
            with patch("app.database.DB_PATH", Path(temp_dir) / "shadow.sqlite3"):
                init_db()
                with connect() as conn:
                    columns = {row["name"] for row in conn.execute("pragma table_info(chat_metrics)").fetchall()}
                self.assertTrue({"execution_mode", "shadow_mode", "mode_agreement"} <= columns)

                empty = get_chat_metrics_summary()
                self.assertEqual(empty["mode_agreement_samples"], 0)
                self.assertEqual(empty["mode_agreement_rate"], 1.0)

                record_chat_metric(**base, execution_mode="retrieval", shadow_mode="retrieval", mode_agreement=True)
                record_chat_metric(**base, execution_mode="retrieval", shadow_mode="agentic", mode_agreement=False)
                record_chat_metric(**base, execution_mode="retrieval", shadow_mode="agentic", mode_agreement=False)
                record_chat_metric(**{**base, "outcome": "error"})  # 旧调用方 / 错误请求：未评估
                summary = get_chat_metrics_summary()

        self.assertEqual(summary["total_requests"], 4)
        self.assertEqual(summary["mode_agreement_samples"], 3)
        self.assertAlmostEqual(summary["mode_agreement_rate"], 1 / 3)
        self.assertEqual(summary["execution_mode_usage"], {"retrieval": 3})
        self.assertEqual(summary["shadow_mode_usage"], {"retrieval": 1, "agentic": 2})
        self.assertEqual(summary["mode_disagreements"], {"standard->agentic": 2})

    def test_chat_route_records_shadow_routing_end_to_end(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            with patch("app.database.DB_PATH", Path(temp_dir) / "shadow.sqlite3"):
                ingest_document("project.md", RELEVANT_TEXT)
                client = TestClient(app)
                for workflow_mode in ("standard", "agentic"):
                    response = client.post(
                        "/chat",
                        json={
                            "question": "客户A的项目为什么延期？",
                            "answer_mode": "local",
                            "retriever_mode": "keyword",
                            "workflow_mode": workflow_mode,
                        },
                    )
                    self.assertEqual(response.status_code, 200)
                summary = client.get("/metrics/summary").json()

        self.assertEqual(summary["mode_agreement_samples"], 2)
        self.assertEqual(summary["mode_agreement_rate"], 0.5)
        self.assertEqual(summary["execution_mode_usage"], {"retrieval": 1, "agentic": 1})
        self.assertEqual(summary["mode_disagreements"], {"standard->agentic": 1})


if __name__ == "__main__":
    unittest.main()
