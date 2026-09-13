"""Evidence character budget (optimisation plan 0.5).

Sources follow the final retrieval rank (``MAX_SOURCES`` in ``rag.py``), then are cut
to a per-source cap and a total cap.  Trimming prefers a sentence boundary,
marks the excerpt with an ellipsis, and never reorders sources; when the total
budget leaves less than ``MIN_TAIL_CHARS`` for the next source that source and
everything after it (lower ranked) is dropped.  What the model sees is what
the evidence check and citation review see, because both run on the budgeted
sources. Long media segments and expanded parent sections can both hit the cap.
"""

from __future__ import annotations

from dataclasses import dataclass

from app.config import EvidenceBudgetSettings, get_evidence_budget_settings
from app.models import Source, TraceStep

SENTENCE_BREAKS = "。！？；!?;\n"
ELLIPSIS = "…"
# A source that would receive less than this from the total budget is dropped
# instead of being reduced to a fragment nobody can cite.
MIN_TAIL_CHARS = 120
# Prefer a sentence boundary only if it keeps at least this share of the cap.
MIN_BOUNDARY_RATIO = 0.6


@dataclass(frozen=True)
class BudgetedEvidence:
    sources: list[Source]
    budget: EvidenceBudgetSettings
    original_chars: int
    budgeted_chars: int
    trimmed: tuple[str, ...] = ()
    dropped: tuple[str, ...] = ()

    @property
    def changed(self) -> bool:
        return bool(self.trimmed or self.dropped)

    def describe(self) -> str:
        text = (
            f"证据预算：{len(self.sources)} 个来源共 {self.budgeted_chars}/{self.budget.total_chars} 字符"
            f"（单来源上限 {self.budget.per_source_chars}）。"
        )
        if not self.changed:
            return text + "按最终排名选出的来源均在预算内，未裁剪。"
        if self.trimmed:
            text += f"裁剪 {len(self.trimmed)} 个：{'；'.join(self.trimmed)}。"
        if self.dropped:
            text += f"预算耗尽后丢弃 {len(self.dropped)} 个排名靠后的来源：{'；'.join(self.dropped)}。"
        return text + f"原始共 {self.original_chars} 字符。"

    def trace_step(self, name: str = "evidence_budget") -> TraceStep:
        return TraceStep(
            name=name,
            status="trimmed" if self.changed else "ok",
            detail=self.describe(),
        )


def source_label(source: Source) -> str:
    return f"{source.filename}#chunk{source.chunk_index}"


def trim_content(text: str, cap: int) -> str:
    """Cut ``text`` to at most ``cap`` characters, at a sentence end when one is near."""
    if len(text) <= cap:
        return text
    window = text[: cap - len(ELLIPSIS)]
    boundary = max(window.rfind(mark) for mark in SENTENCE_BREAKS)
    if boundary >= int(cap * MIN_BOUNDARY_RATIO):
        window = window[: boundary + 1]
    return window.rstrip() + ELLIPSIS


def apply_evidence_budget(
    sources: list[Source], budget: EvidenceBudgetSettings | None = None
) -> BudgetedEvidence:
    settings = budget or get_evidence_budget_settings()
    kept: list[Source] = []
    trimmed: list[str] = []
    dropped: list[str] = []
    remaining = settings.total_chars
    original_chars = sum(len(source.content) for source in sources)

    for source in sources:
        if remaining < MIN_TAIL_CHARS:
            dropped.append(source_label(source))
            continue
        cap = min(settings.per_source_chars, remaining)
        content = source.content
        if len(content) <= cap:
            kept.append(source)
            remaining -= len(content)
            continue
        cut = trim_content(content, cap)
        kept.append(source.model_copy(update={"content": cut}))
        trimmed.append(f"{source_label(source)} {len(content)}→{len(cut)}")
        remaining -= len(cut)

    return BudgetedEvidence(
        sources=kept,
        budget=settings,
        original_chars=original_chars,
        budgeted_chars=sum(len(source.content) for source in kept),
        trimmed=tuple(trimmed),
        dropped=tuple(dropped),
    )


__all__ = [
    "ELLIPSIS",
    "MIN_TAIL_CHARS",
    "BudgetedEvidence",
    "apply_evidence_budget",
    "source_label",
    "trim_content",
]
