import json
import unittest
from unittest.mock import Mock

from app.architecture.context import RequestContext
from app.architecture.manifest import PANORAMA_LAYERS, panorama_manifest
from app.architecture.orchestration import (
    STANDARD_SKIPPED_STEPS,
    ClarificationExecutor,
    ConversationInput,
    ConversationOrchestrator,
    ExecutorRegistry,
    build_default_chain,
)
from app.architecture.planning import ExecutionPlan, StageTimer
from app.auth import ActorPrincipal
from app.models import ChatResponse, TraceStep
from app.retrievers import RetrievalScope


class ArchitectureBoundaryTests(unittest.TestCase):
    def test_panorama_manifest_describes_six_layers(self) -> None:
        manifest = panorama_manifest()
        self.assertEqual(
            [layer["key"] for layer in manifest],
            ["orchestration", "retrieval", "execution", "knowledge", "governance", "guardrails"],
        )
        self.assertEqual(len(manifest), len(PANORAMA_LAYERS))
        for layer in manifest:
            self.assertTrue(layer["title"])
            self.assertTrue(layer["responsibility"])
            self.assertTrue(layer["modules"])

    def test_request_context_preserves_signed_scope(self) -> None:
        principal = ActorPrincipal(
            user_id="user-7",
            tenant_id="tenant-9",
            role="operator",
            auth_mode="jwt",
            workspace_type="personal",
        )

        context = RequestContext.from_principal(principal)
        self.assertEqual(context.tenant_id, "tenant-9")
        self.assertEqual(context.owner_id, "user-7")
        self.assertEqual(context.actor_user, "user-7")
        self.assertEqual(context.retrieval_scope(["asset-1", "asset-1"]).asset_ids, ("asset-1",))

    def test_orchestrator_routes_standard_and_agentic_without_scope_leak(self) -> None:
        standard = Mock(return_value=ChatResponse(answer="standard", sources=[]))
        agentic = Mock(return_value=ChatResponse(answer="agentic", sources=[]))
        orchestrator = ConversationOrchestrator(
            standard_handler=standard,
            agentic_handler=agentic,
        )

        orchestrator.answer(ConversationInput(
            question="状态？",
            workflow_mode="standard",
            answer_mode="local",
            retriever_mode="keyword",
        ))
        standard.assert_called_once_with(
            "状态？", answer_mode="local", retriever_mode="keyword",
        )

        orchestrator.answer(ConversationInput(
            question="为什么延期？",
            workflow_mode="agentic",
            answer_mode="local",
            retriever_mode="hybrid",
            actor_role="viewer",
            actor_user="user-7",
            workspace_type="team",
            retrieval_scope=RetrievalScope(tenant_id="tenant-9"),
        ))
        agentic.assert_called_once()
        self.assertEqual(agentic.call_args.args, ("为什么延期？",))
        kwargs = dict(agentic.call_args.kwargs)
        plan = kwargs.pop("plan")
        self.assertIsInstance(plan, ExecutionPlan)
        self.assertEqual(plan.mode, "agentic")
        self.assertEqual(
            kwargs,
            dict(
                answer_mode="local",
                retriever_mode="hybrid",
                actor_role="viewer",
                actor_user="user-7",
                workspace_type="team",
                retrieval_scope=RetrievalScope(tenant_id="tenant-9"),
            ),
        )


class ExecutionPlanTests(unittest.TestCase):
    def test_plan_is_serializable_and_steps_can_be_skipped(self) -> None:
        chain = build_default_chain()
        plan = chain.run("客户A的项目为什么延期？", "agentic", skip=("classify_intent",))

        self.assertEqual(plan.skipped, ("classify_intent",))
        self.assertEqual(plan.steps, ("decide_mode", "plan_queries"))
        self.assertEqual(plan.mode, "agentic")
        self.assertIn("客户A的项目为什么延期？", plan.queries)
        self.assertTrue(all(step.duration_ms is not None for step in plan.trace))

        payload = json.loads(plan.to_json())
        self.assertEqual(payload["mode"], "agentic")
        self.assertEqual(payload["skipped"], ["classify_intent"])
        self.assertEqual(plan.trace_step().name, "execution_plan")

        with self.assertRaises(ValueError):
            chain.run("客户A", "agentic", skip=("no_such_step",))

    def test_chain_decides_clarify_tool_only_and_retrieval(self) -> None:
        chain = build_default_chain()
        self.assertEqual(chain.run("为什么？", "agentic").mode, "clarify")
        self.assertEqual(chain.run("查询工单 T-1 的状态", "agentic").mode, "tool_only")
        standard = chain.run("客户A为什么延期？", "standard", skip=STANDARD_SKIPPED_STEPS)
        self.assertEqual(standard.mode, "retrieval")
        self.assertEqual(standard.skipped, STANDARD_SKIPPED_STEPS)

    def test_orchestrator_clarifies_without_calling_handlers(self) -> None:
        standard = Mock()
        agentic = Mock()
        orchestrator = ConversationOrchestrator(standard_handler=standard, agentic_handler=agentic)

        response = orchestrator.answer(ConversationInput(
            question="为什么？",
            workflow_mode="agentic",
            answer_mode="local",
            retriever_mode="keyword",
        ))

        standard.assert_not_called()
        agentic.assert_not_called()
        self.assertEqual(response.sources, [])
        assert response.agent_summary is not None
        self.assertEqual(response.agent_summary.execution_mode, "clarify")
        self.assertEqual(response.agent_summary.clarify_question, response.answer)
        self.assertIn("Clarification Agent", response.agent_summary.agents)
        self.assertEqual(
            [step.name for step in response.trace][-3:],
            ["mode_decision", "execution_plan", "answer"],
        )

    def test_tool_only_question_reaches_agentic_handler_with_tool_only_plan(self) -> None:
        agentic = Mock(return_value=ChatResponse(answer="tool", sources=[]))
        orchestrator = ConversationOrchestrator(standard_handler=Mock(), agentic_handler=agentic)

        orchestrator.answer(ConversationInput(
            question="查询工单 T-1 的状态",
            workflow_mode="agentic",
            answer_mode="local",
            retriever_mode="keyword",
        ))

        agentic.assert_called_once()
        self.assertEqual(agentic.call_args.kwargs["plan"].mode, "tool_only")

    def test_registry_rejects_duplicates_and_unknown_modes(self) -> None:
        registry = ExecutorRegistry([ClarificationExecutor()])
        self.assertEqual(registry.modes(), ("clarify",))
        with self.assertRaises(ValueError):
            registry.register(ClarificationExecutor())
        with self.assertRaises(ValueError):
            registry.get("no_such_mode")

    def test_stage_timer_stamps_only_unstamped_new_steps(self) -> None:
        trace: list[TraceStep] = []
        timer = StageTimer(trace)
        trace.append(TraceStep(name="a", status="ok", detail=""))
        timer.mark()
        trace.append(TraceStep(name="b", status="ok", detail="", duration_ms=5.0))
        trace.append(TraceStep(name="c", status="ok", detail=""))
        timer.mark()

        self.assertIsNotNone(trace[0].duration_ms)
        self.assertGreaterEqual(trace[0].duration_ms or 0.0, 0.0)
        self.assertEqual(trace[1].duration_ms, 5.0)
        self.assertIsNotNone(trace[2].duration_ms)
