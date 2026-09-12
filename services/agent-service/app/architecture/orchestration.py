"""Conversation orchestration boundary (the panorama's 编排中心).

A ``PreparationChain`` turns the request into one frozen ``ExecutionPlan``
(classification, query planning, mode decision), and an ``ExecutorRegistry``
dispatches on ``plan.mode``.  The proven implementations in ``agentic_rag``
and ``rag`` remain the executors; HTTP handlers stay unaware of them.
``workflow_mode`` is kept as a backwards-compatible input, but the server's
plan has the final say (a question without any content anchor is clarified
instead of retrieved, a direct ticket operation skips retrieval).
"""

from __future__ import annotations

from collections.abc import Callable, Iterable
from dataclasses import dataclass
from typing import Protocol

from app.agentic_rag import CLASSIFY_STEP, PLAN_QUERIES_STEP, answer_agentic_question
from app.architecture.planning import (
    DECIDE_MODE_STEP,
    DEFAULT_CLARIFY_QUESTION,
    ExecutionPlan,
    PreparationChain,
)
from app.call_limits import request_call_limits
from app.config import CallLimits
from app.models import AgentSummary, ChatResponse, TraceStep
from app.rag import answer_question, deduplicate_preserve_order
from app.retrievers import RetrievalScope

# Explicit standard requests keep the cheap single-round path: no router model
# call, no multi-query planning.  Only the mode decision (clarify gate) runs.
STANDARD_SKIPPED_STEPS = ("classify_intent", "plan_queries")


@dataclass(frozen=True)
class ConversationInput:
    question: str
    workflow_mode: str
    answer_mode: str
    retriever_mode: str
    actor_role: str = "operator"
    actor_user: str = "anonymous"
    workspace_type: str = "team"
    retrieval_scope: RetrievalScope | None = None


class Executor(Protocol):
    mode: str

    def execute(self, request: ConversationInput, plan: ExecutionPlan) -> ChatResponse: ...


class ExecutorRegistry:
    """One executor per execution mode; unknown modes fail loudly."""

    def __init__(self, executors: Iterable[Executor] = ()) -> None:
        self._executors: dict[str, Executor] = {}
        for executor in executors:
            self.register(executor)

    def register(self, executor: Executor) -> None:
        if executor.mode in self._executors:
            raise ValueError(f"executor for mode {executor.mode!r} already registered")
        self._executors[executor.mode] = executor

    def get(self, mode: str) -> Executor:
        try:
            return self._executors[mode]
        except KeyError as exc:
            raise ValueError(f"no executor registered for mode {mode!r}") from exc

    def modes(self) -> tuple[str, ...]:
        return tuple(self._executors)


@dataclass(frozen=True)
class RetrievalExecutor:
    """Single-round RAG (``rag.answer_question``)."""

    handler: Callable[..., ChatResponse]
    mode = "retrieval"

    def execute(self, request: ConversationInput, plan: ExecutionPlan) -> ChatResponse:
        kwargs = dict(answer_mode=request.answer_mode, retriever_mode=request.retriever_mode)
        if request.retrieval_scope is not None:
            kwargs["scope"] = request.retrieval_scope
        response = self.handler(request.question, **kwargs)
        # 单轮路径不接触计划对象：把计划步骤与计划本身放到 trace 开头，回放时与 agentic 一样可见。
        response.trace[:0] = [*plan.trace, plan.trace_step()]
        return response


@dataclass(frozen=True)
class AgenticExecutor:
    """Multi-round retrieval + graph + tools + citation review (``agentic_rag``)."""

    handler: Callable[..., ChatResponse]
    mode = "agentic"

    def execute(self, request: ConversationInput, plan: ExecutionPlan) -> ChatResponse:
        kwargs = dict(
            answer_mode=request.answer_mode,
            retriever_mode=request.retriever_mode,
            actor_role=request.actor_role,
            actor_user=request.actor_user,
            workspace_type=request.workspace_type,
        )
        if request.retrieval_scope is not None:
            kwargs["retrieval_scope"] = request.retrieval_scope
        kwargs["plan"] = plan
        return self.handler(request.question, **kwargs)


@dataclass(frozen=True)
class ToolOnlyExecutor(AgenticExecutor):
    """Direct ticket operations reuse the agentic runtime with retrieval skipped."""

    mode = "tool_only"


class ClarificationExecutor:
    """Return the clarification question: no retrieval, no model call."""

    mode = "clarify"

    def execute(self, request: ConversationInput, plan: ExecutionPlan) -> ChatResponse:
        question = plan.clarify_question or DEFAULT_CLARIFY_QUESTION
        trace = [
            *plan.trace,
            plan.trace_step(),
            TraceStep(
                name="answer",
                status="clarify",
                detail="Clarification Agent 直接返回澄清问题，未检索、未调用模型。",
                duration_ms=0.0,
            ),
        ]
        summary = AgentSummary(
            workflow=request.workflow_mode,
            intent=plan.intent,
            complexity=plan.complexity,
            retrieval_rounds=0,
            queries=list(plan.queries),
            evidence_status="not_required",
            citation_status="not_applicable",
            agents=deduplicate_preserve_order([*plan.agents, "Clarification Agent"]),
            execution_mode="clarify",
            clarify_question=question,
        )
        return ChatResponse(answer=question, sources=[], trace=trace, agent_summary=summary)


def build_default_chain() -> PreparationChain:
    return PreparationChain([CLASSIFY_STEP, DECIDE_MODE_STEP, PLAN_QUERIES_STEP])


def build_default_registry(
    *,
    agentic_handler: Callable[..., ChatResponse],
    standard_handler: Callable[..., ChatResponse],
) -> ExecutorRegistry:
    return ExecutorRegistry(
        [
            RetrievalExecutor(standard_handler),
            AgenticExecutor(agentic_handler),
            ToolOnlyExecutor(agentic_handler),
            ClarificationExecutor(),
        ]
    )


class ConversationOrchestrator:
    """Plan once, then run exactly one executor for a conversation turn."""

    def __init__(
        self,
        *,
        agentic_handler: Callable[..., ChatResponse] = answer_agentic_question,
        standard_handler: Callable[..., ChatResponse] = answer_question,
        chain: PreparationChain | None = None,
        registry: ExecutorRegistry | None = None,
        call_limits: CallLimits | None = None,
    ) -> None:
        # Injection keeps this boundary observable by compatibility tests and
        # alternate runtimes without exposing persistence implementation.
        self._chain = chain or build_default_chain()
        self._registry = registry or build_default_registry(
            agentic_handler=agentic_handler, standard_handler=standard_handler
        )
        self._call_limits = call_limits  # None = AGENT_MAX_MODEL_CALLS / AGENT_MAX_TOOL_CALLS

    def plan(self, request: ConversationInput) -> ExecutionPlan:
        skip = STANDARD_SKIPPED_STEPS if request.workflow_mode != "agentic" else ()
        return self._chain.run(request.question, request.workflow_mode, skip=skip)

    def run(self, request: ConversationInput) -> tuple[ChatResponse, ExecutionPlan]:
        """Plan and execute under one per-request call budget; return the plan for metrics."""
        with request_call_limits(limits=self._call_limits) as counter:
            plan = self.plan(request)
            response = self._registry.get(plan.mode).execute(request, plan)
        if counter.attempted:
            response.trace.append(counter.trace_step())
        return response, plan

    def answer(self, request: ConversationInput) -> ChatResponse:
        return self.run(request)[0]


def run_chat(
    question: str,
    *,
    workflow_mode: str,
    answer_mode: str,
    retriever_mode: str,
    actor_role: str,
    actor_user: str,
    workspace_type: str,
    retrieval_scope: RetrievalScope | None = None,
    agentic_handler: Callable[..., ChatResponse] = answer_agentic_question,
    standard_handler: Callable[..., ChatResponse] = answer_question,
) -> tuple[ChatResponse, ExecutionPlan]:
    """Route entry: the response plus the plan the metrics row is built from."""
    return ConversationOrchestrator(
        agentic_handler=agentic_handler,
        standard_handler=standard_handler,
    ).run(
        ConversationInput(
            question=question,
            workflow_mode=workflow_mode,
            answer_mode=answer_mode,
            retriever_mode=retriever_mode,
            actor_role=actor_role,
            actor_user=actor_user,
            workspace_type=workspace_type,
            retrieval_scope=retrieval_scope,
        )
    )


def answer_chat(
    question: str,
    *,
    workflow_mode: str,
    answer_mode: str,
    retriever_mode: str,
    actor_role: str,
    actor_user: str,
    workspace_type: str,
    retrieval_scope: RetrievalScope | None = None,
    agentic_handler: Callable[..., ChatResponse] = answer_agentic_question,
    standard_handler: Callable[..., ChatResponse] = answer_question,
) -> ChatResponse:
    """Compatibility-friendly function: the response only."""
    return run_chat(
        question,
        workflow_mode=workflow_mode,
        answer_mode=answer_mode,
        retriever_mode=retriever_mode,
        actor_role=actor_role,
        actor_user=actor_user,
        workspace_type=workspace_type,
        retrieval_scope=retrieval_scope,
        agentic_handler=agentic_handler,
        standard_handler=standard_handler,
    )[0]
