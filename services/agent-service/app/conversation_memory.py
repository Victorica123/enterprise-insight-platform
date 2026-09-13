"""Bounded topic memory. Previous answers are never evidence for a new turn."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from typing import Protocol

from app.conversation_store import ConversationLease, read_memory
from app.llm import is_llm_configured
from app.llm_client import create_chat_completion
from app.models import TraceStep
from app.prompts import load_prompt, render_prompt

_ENTITY = re.compile(r"(?:客户|项目)\s*[A-Za-z0-9][A-Za-z0-9_-]*", re.IGNORECASE)
_FOLLOWUP = re.compile(r"它|他们|这个|该项目|该客户|上述|那.{0,8}(?:呢|谁|多少|如何)|^(?:负责人|什么时候|还有|风险呢|原因呢)")


class MemoryStrategy(Protocol):
    def context(self, turns: list[dict], summary: str = "") -> str: ...


class NoMemory:
    def context(self, turns: list[dict], summary: str = "") -> str:
        return ""


class WindowMemory:
    def context(self, turns: list[dict], summary: str = "") -> str:
        return "\n".join(str(turn["rewritten_question"])[:550] for turn in turns[-4:])[-2200:]


class SummaryMemory(WindowMemory):
    def context(self, turns: list[dict], summary: str = "") -> str:
        return summary[-1400:] + "\n" + super().context(turns)


@dataclass(frozen=True)
class PreparedMemory:
    question: str
    summary: str
    summary_through: int
    trace: TraceStep
    prompt_tokens: int = 0
    completion_tokens: int = 0
    recent_questions: tuple[str, ...] = ()


def prepare_memory(question: str, mode: str, lease: ConversationLease, *, allow_model: bool) -> PreparedMemory:
    turns = read_memory(lease) if mode != "none" else []
    summary, through = lease.summary, lease.summary_through
    summary_status = "unchanged"
    prompt_tokens = completion_tokens = 0
    if mode == "summary":
        older = read_memory(lease, older=True)
        if older:
            text = "\n".join(turn["rewritten_question"][:550] for turn in older)
            summary = (summary + "\n" + text)[-1400:]
            through = older[-1]["turn"]
            summary_status = "rules"
            if allow_model and is_llm_configured():
                try:
                    result = create_chat_completion(messages=[
                        {"role": "system", "content": load_prompt("memory_summary_system")},
                        {"role": "user", "content": render_prompt("memory_summary_user", previous_summary=lease.summary, turns=text)},
                    ], temperature=0, response_format={"type": "json_object"}, purpose="memory_summary")
                    usage = getattr(result, "usage", None)
                    prompt_tokens = int(getattr(usage, "prompt_tokens", 0) or 0)
                    completion_tokens = int(getattr(usage, "completion_tokens", 0) or 0)
                    payload = json.loads(result.choices[0].message.content or "{}")
                    if isinstance(payload, dict) and isinstance(payload.get("summary"), str):
                        proposed = payload["summary"][:1400]
                        allowed = {re.sub(r"\s+", "", value).lower() for value in _ENTITY.findall(lease.summary + "\n" + text)}
                        proposed_topics = {re.sub(r"\s+", "", value).lower() for value in _ENTITY.findall(proposed)}
                        if proposed_topics <= allowed:
                            summary = proposed
                            summary_status = "model"
                        else:
                            summary_status = "rules_fallback"
                except Exception:
                    summary_status = "rules_fallback"
    strategy = {"none": NoMemory(), "window": WindowMemory(), "summary": SummaryMemory()}[mode]
    context = strategy.context(turns, summary)
    rewritten = question
    # Only copy a literal topic identifier already present in authorized user turns.
    # Never copy an old answer, tool instruction, or model-generated fact into a new request.
    if context and _FOLLOWUP.search(question) and not _ENTITY.search(question):
        # Prefer the last turn with a literal topic. A comparison of two topics
        # does not make the second topic the referent of an ambiguous pronoun.
        identifiers: list[str] = []
        candidates = [turn["rewritten_question"] for turn in reversed(turns)]
        if mode == "summary":
            candidates.append(summary)
        for candidate in candidates:
            identifiers = list(dict.fromkeys(re.sub(r"\s+", "", value) for value in _ENTITY.findall(candidate)))
            if identifiers:
                break
        if len(identifiers) == 1:
            topic = identifiers[0]
            rewritten = re.sub(r"该项目|这个项目|该客户|这个客户|它们|他们|它", topic, question)
            if rewritten == question:
                rewritten = f"关于{topic}，{question}"
    return PreparedMemory(rewritten, summary, through, TraceStep(
        name="conversation_memory", status="rewritten" if rewritten != question else mode,
        detail=f"使用最近 {len(turns)} 轮主题提示；历史回答不作为证据。摘要策略：{summary_status}。",
    ), prompt_tokens, completion_tokens,
        recent_questions=tuple(str(turn["rewritten_question"])[:550] for turn in turns))
