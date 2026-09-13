"""Expand ranked children within their authorized document and section."""

from __future__ import annotations

import re
from collections.abc import Iterable

from app.chunk_index import Chunk, RetrievalScope, load_chunk_index
from app.config import get_evidence_budget_settings
from app.models import Source
from app.retrievers import RetrievalHit
from app.text import title_term_boost

_TOPIC = re.compile(r"(?:客户|项目)\s*[A-Za-z0-9][A-Za-z0-9_-]*", re.IGNORECASE)


def _named_topics(text: str) -> set[str]:
    return {re.sub(r"\s+", "", value).lower() for value in _TOPIC.findall(text)}


def _matches_topics(wanted: set[str], chunk: Chunk) -> bool:
    named = _named_topics(f"{chunk.title} {chunk.content}")
    return not any(
        (targets := {topic for topic in wanted if topic.startswith(kind)})
        and (candidates := {topic for topic in named if topic.startswith(kind)})
        and not targets.intersection(candidates)
        for kind in ("客户", "项目")
    )


def filter_topic_hits(question: str, hits: Iterable[RetrievalHit]) -> list[RetrievalHit]:
    """Exclude evidence naming a different explicit customer/project before Top-K.

    Shared policy documents without named topics remain eligible. The existing
    evidence gate still requires the question's explicit anchors to be present.
    This is relevance filtering after authorization, never a permission check.
    """
    wanted = _named_topics(question)
    if not wanted:
        return list(hits)
    return [hit for hit in hits if _matches_topics(wanted, hit.chunk)]


def rank_evidence_hits(question: str, hits: Iterable[RetrievalHit]) -> list[RetrievalHit]:
    """Keep hybrid's final rank through Top-K; score still controls evidence gates.

    Keyword/embedding-only callers have no final fusion rank and retain their
    existing title prior. Stable ties also preserve first-seen order on retries.
    """
    return sorted(
        filter_topic_hits(question, (hit for hit in hits if hit.score > 0)),
        key=lambda hit: (0, hit.selection_rank) if hit.selection_rank is not None
        else (1, -(hit.score + title_term_boost(question, hit.chunk.title))),
    )


def expand_parent_sources(
    sources: list[Source], scope: RetrievalScope | None = None, *, chunks: tuple[Chunk, ...] | None = None,
    question: str = "",
) -> list[Source]:
    if not any(source.parent_key and source.source_type == "document" for source in sources):
        return sources
    authorized = chunks if chunks is not None else load_chunk_index(scope).chunks
    by_key = {(chunk.document_id, chunk.chunk_index): chunk for chunk in authorized}
    cap = get_evidence_budget_settings().per_source_chars
    wanted = _named_topics(question)
    consumed: set[tuple[str, int]] = set()
    expanded: list[Source] = []
    for source in sources:
        key = source.document_id, source.chunk_index
        if key in consumed:
            continue
        if not source.parent_key or source.source_type == "video":
            expanded.append(source)
            continue
        anchor = by_key.get(key)
        if anchor is None or not _matches_topics(wanted, anchor):
            # A document revoked between retrieval and expansion cannot re-enter evidence.
            continue
        chosen = {source.chunk_index: anchor}
        content = source.content
        # Only adjacent siblings; never merge across a section, document, or video segment.
        for direction in (1, -1):
            position = source.chunk_index + direction
            while True:
                sibling = by_key.get((source.document_id, position))
                if (sibling is None or sibling.parent_key != source.parent_key
                        or sibling.source_type == "video" or sibling.tenant_id != anchor.tenant_id
                        or sibling.owner_id != anchor.owner_id or (source.document_id, position) in consumed
                        or not _matches_topics(wanted, sibling)):
                    break
                candidate = dict(chosen)
                candidate[position] = sibling
                merged = join_overlapping([candidate[index].content for index in sorted(candidate)])
                if len(merged) > cap:
                    break
                chosen, content = candidate, merged
                position += direction
        indices = sorted(chosen)
        consumed.update((source.document_id, index) for index in indices)
        expanded.append(source.model_copy(update={"content": content, "chunk_indices": indices}))
    return expanded


def join_overlapping(parts: list[str]) -> str:
    merged = ""
    for part in parts:
        if not merged:
            merged = part
            continue
        overlap = next((size for size in range(min(160, len(merged), len(part)), 0, -1)
                        if merged.endswith(part[:size])), 0)
        merged += part[overlap:] if overlap else "\n" + part
    return merged
