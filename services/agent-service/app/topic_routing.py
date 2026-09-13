"""Clarify competing authorized topics, never competing compatible intents.

The reference confidence formula describes document-domain candidates. Risk
and cause are often both needed, so treating those intents as competing topics
would incorrectly clarify an otherwise answerable question.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass

from app.chunk_index import RetrievalScope, load_chunk_index
from app.models import TraceStep
from app.text import extract_search_terms

_ENTITY = re.compile(r"(?:客户|项目)\s*[A-Za-z0-9][A-Za-z0-9_-]*", re.IGNORECASE)
_MULTI_TOPIC = ("分别", "比较", "对比", "各个", "所有", "全部", "之间")


@dataclass(frozen=True)
class TopicCandidate:
    topic: str
    score: float
    document_count: int = 1


@dataclass(frozen=True)
class TopicDecision:
    reason: str
    confidence: float
    candidates: tuple[TopicCandidate, ...]
    question: str | None = None

    def trace_step(self) -> TraceStep:
        return TraceStep(name="domain_route", status="clarify" if self.question else "ok", detail=json.dumps({
            "reason": self.reason, "confidence": round(self.confidence, 4),
            "candidates": [{"topic": item.topic, "score": item.score} for item in self.candidates[:3]],
        }, ensure_ascii=False))


def assess_topic_candidates(candidates: list[TopicCandidate]) -> TopicDecision:
    ranked = tuple(sorted((item for item in candidates if item.score > 0), key=lambda item: (-item.score, item.topic)))
    if not ranked:
        return TopicDecision("no_candidates", 0.0, ())
    if len(ranked) == 1 and ranked[0].document_count:
        return TopicDecision("single_candidate", 1.0, ranked)
    top = ranked[0]
    second = ranked[1].score if len(ranked) > 1 else 0.0
    confidence = top.score / max(10.0, top.score + second + 5.0)
    reason = "confident"
    if not top.document_count:
        reason = "no_documents"
    elif confidence < 0.55:
        reason = "low_relative_confidence"
    elif len(ranked) > 1 and top.score - second <= 3 and top.topic != ranked[1].topic:
        reason = "close_competing_topics"
    question = None
    if reason != "confident":
        labels = "、".join(item.topic for item in ranked[:3] if item.document_count)
        question = f"请明确您要了解的客户或项目（{labels}），我会据此检索对应证据。" if labels else "请补充客户或项目名称，以及对应资料。"
    return TopicDecision(reason, confidence, ranked, question)


def route_authorized_topics(question: str, scope: RetrievalScope | None) -> TopicDecision | None:
    # Explicit entities and deliberate cross-topic questions are not ambiguous.
    if scope is None or _ENTITY.search(question) or any(term in question for term in _MULTI_TOPIC):
        return None
    if not any(term in question for term in ("项目", "客户", "它", "这个", "该", "负责人")):
        return None
    terms = extract_search_terms(question)
    grouped: dict[str, tuple[float, set[str]]] = {}
    for chunk in load_chunk_index(scope).chunks:
        entities = {re.sub(r"\s+", "", match).lower() for match in _ENTITY.findall(f"{chunk.title} {chunk.content}")}
        if len(entities) != 1:
            continue
        label = next(iter(entities))
        score = 100 * len(terms.intersection(chunk.search_terms())) / max(1, len(terms))
        best, documents = grouped.get(label, (0.0, set()))
        grouped[label] = max(best, score), documents | {chunk.document_id}
    return assess_topic_candidates([TopicCandidate(label, score, len(documents))
                                    for label, (score, documents) in grouped.items()])
