"""Execution planning: a pluggable preparation chain that yields one ExecutionPlan.

Every step mutates a ``PlanDraft``; the chain records which steps ran, which
were skipped and how long each took.  The resulting ``ExecutionPlan`` is frozen
and JSON-serialisable, gets written into the trace, and is what the executor
registry dispatches on.  ``workflow_mode`` from the request stays a
compatibility input: the server decides the final mode here.
"""

from __future__ import annotations

import json
from collections.abc import Callable, Iterable, Sequence
from dataclasses import dataclass, field
from time import perf_counter

from app.agent_planning import detect_intents, is_complex_question
from app.models import TraceStep
from app.text import CHAR_STOPS, QUESTION_STOP_BIGRAMS, STOP_TERMS, content_anchors

EXECUTION_MODES = ("clarify", "tool_only", "retrieval", "agentic")

DEFAULT_CLARIFY_QUESTION = (
    "您的问题缺少可检索的主题（例如客户、项目、文档或工单名称），"
    "请补充后再问，例如：“客户A的项目为什么延期？”"
)


@dataclass
class PlanDraft:
    """Mutable working copy handed to each chain step."""

    question: str
    requested_mode: str
    intent: str = "general"
    complexity: str = "simple"
    queries: list[str] = field(default_factory=list)
    mode: str | None = None
    mode_reason: str = ""
    clarify_question: str | None = None
    router_prompt_tokens: int = 0
    router_completion_tokens: int = 0
    classified: bool = False
    shadow_mode: str | None = None
    shadow_reason: str = ""
    agents: list[str] = field(default_factory=list)
    trace: list[TraceStep] = field(default_factory=list)


@dataclass(frozen=True)
class ExecutionPlan:
    question: str
    requested_mode: str
    mode: str
    mode_reason: str
    intent: str
    complexity: str
    queries: tuple[str, ...]
    clarify_question: str | None
    shadow_mode: str
    shadow_reason: str
    router_prompt_tokens: int
    router_completion_tokens: int
    steps: tuple[str, ...]
    skipped: tuple[str, ...]
    agents: tuple[str, ...]
    trace: tuple[TraceStep, ...]
    duration_ms: float

    @property
    def mode_agreement(self) -> bool:
        """Did the user's explicit workflow_mode land on what the server would pick itself?"""
        return self.shadow_mode == self.mode

    def to_dict(self) -> dict[str, object]:
        return {
            "requested_mode": self.requested_mode,
            "mode": self.mode,
            "mode_reason": self.mode_reason,
            "intent": self.intent,
            "complexity": self.complexity,
            "queries": list(self.queries),
            "clarify_question": self.clarify_question,
            "shadow_mode": self.shadow_mode,
            "shadow_reason": self.shadow_reason,
            "mode_agreement": self.mode_agreement,
            "steps": list(self.steps),
            "skipped": list(self.skipped),
            "router_prompt_tokens": self.router_prompt_tokens,
            "router_completion_tokens": self.router_completion_tokens,
            "duration_ms": round(self.duration_ms, 3),
        }

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), ensure_ascii=False, separators=(",", ":"))

    def trace_step(self) -> TraceStep:
        """The plan itself as a trace entry, so a logged turn can be replayed."""
        return TraceStep(name="execution_plan", status="ok", detail=self.to_json())


PlanStepFn = Callable[[PlanDraft], None]


@dataclass(frozen=True)
class ChainStep:
    name: str
    run: PlanStepFn


class PreparationChain:
    """Ordered, individually skippable steps that each refine the draft."""

    def __init__(self, steps: Sequence[ChainStep]) -> None:
        names = [step.name for step in steps]
        if len(set(names)) != len(names):
            raise ValueError(f"duplicate chain step names: {names}")
        self._steps = tuple(steps)

    @property
    def step_names(self) -> tuple[str, ...]:
        return tuple(step.name for step in self._steps)

    def run(
        self,
        question: str,
        requested_mode: str,
        *,
        skip: Iterable[str] = (),
    ) -> ExecutionPlan:
        skip_set = set(skip)
        unknown = skip_set - set(self.step_names)
        if unknown:
            raise ValueError(f"unknown chain steps to skip: {sorted(unknown)}")

        draft = PlanDraft(question=question, requested_mode=requested_mode)
        executed: list[str] = []
        skipped: list[str] = []
        chain_started = perf_counter()
        for step in self._steps:
            if step.name in skip_set:
                skipped.append(step.name)
                continue
            before = len(draft.trace)
            started = perf_counter()
            step.run(draft)
            elapsed = round((perf_counter() - started) * 1000, 3)
            for trace_step in draft.trace[before:]:
                if trace_step.duration_ms is None:
                    trace_step.duration_ms = elapsed
            executed.append(step.name)

        if draft.mode is None:
            draft.mode = default_mode(draft.requested_mode)
            draft.mode_reason = "fallback_requested_mode"
        if draft.shadow_mode is None:
            draft.shadow_mode, draft.shadow_reason = shadow_decision(draft.question)

        return ExecutionPlan(
            question=draft.question,
            requested_mode=draft.requested_mode,
            mode=draft.mode,
            mode_reason=draft.mode_reason,
            intent=draft.intent,
            complexity=draft.complexity,
            queries=tuple(draft.queries),
            clarify_question=draft.clarify_question,
            shadow_mode=draft.shadow_mode,
            shadow_reason=draft.shadow_reason,
            router_prompt_tokens=draft.router_prompt_tokens,
            router_completion_tokens=draft.router_completion_tokens,
            steps=tuple(executed),
            skipped=tuple(skipped),
            agents=tuple(draft.agents),
            trace=tuple(draft.trace),
            duration_ms=(perf_counter() - chain_started) * 1000,
        )


def default_mode(requested_mode: str) -> str:
    return "agentic" if requested_mode == "agentic" else "retrieval"


_TOOL_ONLY_KEYWORDS = (
    "查工单",
    "查询工单",
    "工单列表",
    "有哪些工单",
    "更新工单",
    "修改状态",
    "关闭工单",
    "解决工单",
)
_TOOL_CREATE_KEYWORDS = ("创建工单", "生成工单", "帮我创建", "建一个工单")
_KNOWLEDGE_KEYWORDS = ("为什么", "原因", "风险", "根据", "资料", "延期", "负责人")


def is_tool_only_question(question: str) -> bool:
    """Direct ticket operations can bypass RAG; knowledge-backed creation cannot."""
    if any(keyword in question for keyword in _TOOL_ONLY_KEYWORDS):
        return True
    create_requested = any(keyword in question for keyword in _TOOL_CREATE_KEYWORDS)
    needs_knowledge = any(keyword in question for keyword in _KNOWLEDGE_KEYWORDS)
    return create_requested and not needs_knowledge


TOOL_KEYWORDS = (
    "工单",
    "创建工单",
    "查工单",
    "查询工单",
    "更新工单",
    "跟进",
    "指派",
    "分配",
    "处理状态",
    "工单状态",
    "ticket",
    "create ticket",
    "query ticket",
    "要不要创建",
    "帮我创建",
    "生成工单",
    "建一个工单",
)


def question_needs_tools(question: str) -> bool:
    """Keyword trigger for the Tool Agent (rules path); the LLM selector may still say no."""
    lowered = question.lower()
    return any(keyword.lower() in lowered for keyword in TOOL_KEYWORDS)


def shadow_decision(
    question: str, *, intent: str | None = None, complexity: str | None = None
) -> tuple[str, str]:
    """The mode the server would pick with no workflow_mode preference (rules only, no model call).

    Policy under evaluation (optimisation plan 0.8): clarify when nothing is
    retrievable, tool_only for direct ticket operations, agentic when the
    question is complex, needs tools or asks for causes / risks, otherwise the
    cheap single-round retrieval.  It is recorded next to the real decision in
    ``chat_metrics`` so an automatic mode can be judged on real traffic before
    it is ever switched on.  Classification from the chain is reused when the
    classify step ran; otherwise the rule router decides.
    """
    if clarification_question(question) is not None:
        return "clarify", "no_content_anchor"
    if is_tool_only_question(question):
        return "tool_only", "direct_ticket_operation"
    intents = detect_intents(question)
    resolved_intent = intent or (intents[0] if intents else "general")
    resolved_complexity = complexity or (
        "complex" if is_complex_question(question, intents) else "simple"
    )
    if resolved_complexity == "complex":
        return "agentic", "complex_question"
    if question_needs_tools(question):
        return "agentic", "tool_assisted"
    if resolved_intent in {"risk", "causal"}:
        return "agentic", "reasoning_intent"
    return "retrieval", "simple_lookup"


def clarification_question(question: str) -> str | None:
    """Rule-based clarify gate: no content anchor means nothing to retrieve or route on.

    The relative-confidence formula from the optimisation plan (0.6) will refine
    this; for now only anchor-less questions such as "为什么？" are bounced back.
    """
    anchors = [
        anchor
        for anchor in content_anchors(question)
        if anchor not in STOP_TERMS
        and anchor not in QUESTION_STOP_BIGRAMS
        and anchor not in CHAR_STOPS
    ]
    if anchors:
        return None
    return DEFAULT_CLARIFY_QUESTION


def decide_mode(draft: PlanDraft) -> None:
    """CLARIFY > (explicit standard → RETRIEVAL) > TOOL_ONLY > AGENTIC, plus the shadow decision."""
    if draft.mode is not None:
        return  # an earlier step already decided
    clarify = clarification_question(draft.question)
    if clarify is not None:
        draft.mode, draft.mode_reason = "clarify", "no_content_anchor"
        draft.clarify_question = clarify
    elif draft.requested_mode != "agentic":
        # workflow_mode=standard remains an explicit single-round retrieval request.
        draft.mode, draft.mode_reason = "retrieval", "requested_standard"
    elif is_tool_only_question(draft.question):
        draft.mode, draft.mode_reason = "tool_only", "direct_ticket_operation"
    else:
        draft.mode, draft.mode_reason = "agentic", "requested_agentic"
    # 阶段 0.8 影子路由：不改变实际决定，只记录“系统自己会选什么”，供一致率统计
    draft.shadow_mode, draft.shadow_reason = shadow_decision(
        draft.question,
        intent=draft.intent if draft.classified else None,
        complexity=draft.complexity if draft.classified else None,
    )
    agreement = "一致" if draft.shadow_mode == draft.mode else "不一致"
    draft.trace.append(
        TraceStep(
            name="mode_decision",
            status="ok",
            detail=(
                f"执行模式 {draft.mode}（{draft.mode_reason}）；用户请求的 workflow_mode 为 {draft.requested_mode}。"
                f"影子路由：不带 workflow_mode 时系统会选 {draft.shadow_mode}（{draft.shadow_reason}），与实际{agreement}。"
            ),
        )
    )


DECIDE_MODE_STEP = ChainStep(name="decide_mode", run=decide_mode)


class StageTimer:
    """Stamps ``duration_ms`` on trace steps appended since the previous mark."""

    def __init__(self, trace: list[TraceStep]) -> None:
        self._trace = trace
        self._cursor = len(trace)
        self._last = perf_counter()

    def mark(self) -> None:
        now = perf_counter()
        elapsed = round((now - self._last) * 1000, 3)
        for step in self._trace[self._cursor :]:
            if step.duration_ms is None:
                step.duration_ms = elapsed
        self._cursor = len(self._trace)
        self._last = now


__all__ = [
    "DECIDE_MODE_STEP",
    "DEFAULT_CLARIFY_QUESTION",
    "EXECUTION_MODES",
    "TOOL_KEYWORDS",
    "ChainStep",
    "ExecutionPlan",
    "PlanDraft",
    "PlanStepFn",
    "PreparationChain",
    "StageTimer",
    "clarification_question",
    "decide_mode",
    "default_mode",
    "is_tool_only_question",
    "question_needs_tools",
    "shadow_decision",
]
