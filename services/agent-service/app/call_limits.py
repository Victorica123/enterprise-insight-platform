"""Per-request call budget (optimisation plan 0.4): model calls and tool calls.

The counter is bound to the current request with a ``ContextVar`` (the same
pattern ``model_egress`` uses for the tenant).  Code that runs outside a bound
request (admin routes, ticket drafts, analysis jobs) sees no counter and is not
limited.  Reaching a limit never surfaces as an HTTP error: the LLM callers
catch ``CallLimitExceeded`` and fall back to rules / templates, the tool layer
returns a failed ``ToolCallResult`` with status ``limited``, and every denial is
kept on the counter so the orchestrator can write one ``call_limits`` trace
step per request.
"""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from contextvars import ContextVar, Token
from dataclasses import dataclass, field
from typing import Literal

from app.config import CallLimits, get_call_limits
from app.models import TraceStep

CallKind = Literal["model", "tool"]

_KIND_LABELS = {"model": "模型调用", "tool": "工具调用"}


class CallLimitExceeded(RuntimeError):
    """Raised by ``acquire_call`` when the request budget for a call kind is spent."""

    def __init__(self, kind: CallKind, limit: int, label: str = "") -> None:
        suffix = f" ({label})" if label else ""
        super().__init__(f"{kind} call limit of {limit} reached for this request{suffix}")
        self.kind: CallKind = kind
        self.limit = limit
        self.label = label


@dataclass
class LimitCounter:
    """Counts allowed calls per kind and remembers every denied attempt."""

    limits: CallLimits = field(default_factory=get_call_limits)
    model_calls: int = 0
    tool_calls: int = 0
    denials: list[str] = field(default_factory=list)

    def limit_for(self, kind: CallKind) -> int:
        return self.limits.max_model_calls if kind == "model" else self.limits.max_tool_calls

    def used(self, kind: CallKind) -> int:
        return self.model_calls if kind == "model" else self.tool_calls

    def remaining(self, kind: CallKind) -> int:
        return max(0, self.limit_for(kind) - self.used(kind))

    def try_acquire(self, kind: CallKind, *, label: str = "") -> bool:
        """Reserve one call; ``False`` (and a recorded denial) once the budget is spent."""
        if self.used(kind) >= self.limit_for(kind):
            self.denials.append(f"{kind}:{label or '-'}")
            return False
        if kind == "model":
            self.model_calls += 1
        else:
            self.tool_calls += 1
        return True

    def acquire(self, kind: CallKind, *, label: str = "") -> None:
        if not self.try_acquire(kind, label=label):
            raise CallLimitExceeded(kind, self.limit_for(kind), label)

    @property
    def denied_model_calls(self) -> int:
        return sum(1 for item in self.denials if item.startswith("model:"))

    @property
    def denied_tool_calls(self) -> int:
        return sum(1 for item in self.denials if item.startswith("tool:"))

    @property
    def exceeded(self) -> bool:
        return bool(self.denials)

    @property
    def attempted(self) -> bool:
        """True when anything asked for budget, allowed or not."""
        return bool(self.model_calls or self.tool_calls or self.denials)

    def describe(self) -> str:
        parts = [
            f"{_KIND_LABELS['model']} {self.model_calls}/{self.limits.max_model_calls}",
            f"{_KIND_LABELS['tool']} {self.tool_calls}/{self.limits.max_tool_calls}",
        ]
        text = "、".join(parts)
        if not self.denials:
            return f"调用预算：{text}，未超限。"
        denied = "、".join(
            f"{_KIND_LABELS[item.split(':', 1)[0]]}({item.split(':', 1)[1]})" for item in self.denials
        )
        return f"调用预算：{text}；超限被跳过 {len(self.denials)} 次：{denied}。超限调用已降级为规则 / 模板路径。"

    def trace_step(self) -> TraceStep:
        return TraceStep(
            name="call_limits",
            status="degraded" if self.exceeded else "ok",
            detail=self.describe(),
            duration_ms=0.0,
        )


_COUNTER: ContextVar[LimitCounter | None] = ContextVar("call_limit_counter", default=None)


def bind_call_limits(counter: LimitCounter) -> Token[LimitCounter | None]:
    return _COUNTER.set(counter)


def reset_call_limits(token: Token[LimitCounter | None]) -> None:
    _COUNTER.reset(token)


def current_call_limits() -> LimitCounter | None:
    return _COUNTER.get()


@contextmanager
def request_call_limits(
    counter: LimitCounter | None = None, *, limits: CallLimits | None = None
) -> Iterator[LimitCounter]:
    """Bind a fresh (or given) counter for the duration of one request."""
    active = counter if counter is not None else LimitCounter(limits or get_call_limits())
    token = bind_call_limits(active)
    try:
        yield active
    finally:
        reset_call_limits(token)


def try_acquire_call(kind: CallKind, *, label: str = "") -> bool:
    """Budget gate for tool execution: always allowed outside a bound request."""
    counter = _COUNTER.get()
    return True if counter is None else counter.try_acquire(kind, label=label)


def acquire_call(kind: CallKind, *, label: str = "") -> None:
    """Budget gate for model calls: raises ``CallLimitExceeded`` inside a spent request."""
    counter = _COUNTER.get()
    if counter is not None:
        counter.acquire(kind, label=label)


__all__ = [
    "CallKind",
    "CallLimitExceeded",
    "LimitCounter",
    "acquire_call",
    "bind_call_limits",
    "current_call_limits",
    "request_call_limits",
    "reset_call_limits",
    "try_acquire_call",
]
