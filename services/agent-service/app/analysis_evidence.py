from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass

from app import database
from app.retrievers import Chunk, RetrievalScope, get_retriever

ANALYSIS_RETRIEVAL_MODE = "hybrid"
ANALYSIS_SNAPSHOT_LIMIT = 24


@dataclass(frozen=True)
class AnalysisEvidenceSnapshot:
    """Immutable, objective-ranked evidence used for one analysis session."""

    revision: int
    sha256: str
    chunks: tuple[Chunk, ...]
    payload_json: str
    retrieval_mode: str = ANALYSIS_RETRIEVAL_MODE


def build_analysis_evidence_snapshot(
    objective: str,
    scope: RetrievalScope,
    *,
    limit: int = ANALYSIS_SNAPSHOT_LIMIT,
    stable_read_attempts: int = 3,
) -> AnalysisEvidenceSnapshot:
    """Select authorized evidence and freeze it after a stable content-revision read."""

    bounded_limit = max(1, min(limit, ANALYSIS_SNAPSHOT_LIMIT))
    for _ in range(max(1, stable_read_attempts)):
        revision_before = database.get_content_revision()
        result = get_retriever(ANALYSIS_RETRIEVAL_MODE).search([objective], scope)
        revision_after = database.get_content_revision()
        if revision_before != revision_after:
            continue

        selected = [hit for hit in result.hits if hit.score > 0][:bounded_limit]
        entries = [
            {
                "rank": rank,
                "score": hit.score,
                "matched_queries": hit.matched_queries,
                "chunk": _chunk_to_dict(hit.chunk),
            }
            for rank, hit in enumerate(selected, start=1)
        ]
        payload_json = _canonical_json(entries)
        return AnalysisEvidenceSnapshot(
            revision=revision_after,
            sha256=hashlib.sha256(payload_json.encode("utf-8")).hexdigest(),
            chunks=tuple(hit.chunk for hit in selected),
            payload_json=payload_json,
        )

    raise RuntimeError("Evidence changed repeatedly while the analysis snapshot was being created.")


def restore_analysis_evidence_snapshot(
    payload_json: str,
    *,
    revision: int,
    expected_sha256: str,
    retrieval_mode: str,
) -> AnalysisEvidenceSnapshot:
    canonical = _canonical_json(json.loads(payload_json or "[]"))
    actual_sha256 = hashlib.sha256(canonical.encode("utf-8")).hexdigest()
    if expected_sha256 and actual_sha256 != expected_sha256:
        raise ValueError("Analysis evidence snapshot fingerprint mismatch.")
    entries = json.loads(canonical)
    return AnalysisEvidenceSnapshot(
        revision=revision,
        sha256=actual_sha256,
        chunks=tuple(_chunk_from_dict(entry["chunk"]) for entry in entries),
        payload_json=canonical,
        retrieval_mode=retrieval_mode,
    )


def empty_snapshot_sha256() -> str:
    return hashlib.sha256(b"[]").hexdigest()


def _canonical_json(value: object) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _chunk_to_dict(chunk: Chunk) -> dict[str, object]:
    # Embedding vectors are intentionally excluded: resume needs evidence facts,
    # not a duplicate of the retrieval index.
    return {
        "document_id": chunk.document_id,
        "filename": chunk.filename,
        "chunk_index": chunk.chunk_index,
        "content": chunk.content,
        "title": chunk.title,
        "tenant_id": chunk.tenant_id,
        "owner_id": chunk.owner_id,
        "source_type": chunk.source_type,
        "asset_id": chunk.asset_id,
        "segment_id": chunk.segment_id,
        "start_ms": chunk.start_ms,
        "end_ms": chunk.end_ms,
        "speaker": chunk.speaker,
        "origin_type": chunk.origin_type,
        "knowledge_candidate_id": chunk.knowledge_candidate_id,
        "prd_version_id": chunk.prd_version_id,
        "content_sha256": chunk.content_sha256,
    }


def _chunk_from_dict(value: dict[str, object]) -> Chunk:
    return Chunk(
        document_id=str(value["document_id"]),
        filename=str(value["filename"]),
        chunk_index=int(value["chunk_index"]),
        content=str(value["content"]),
        title=str(value.get("title") or ""),
        tenant_id=str(value.get("tenant_id") or "legacy"),
        owner_id=str(value.get("owner_id") or "legacy"),
        source_type=str(value.get("source_type") or "document"),
        asset_id=_optional_str(value.get("asset_id")),
        segment_id=_optional_str(value.get("segment_id")),
        start_ms=_optional_int(value.get("start_ms")),
        end_ms=_optional_int(value.get("end_ms")),
        speaker=_optional_str(value.get("speaker")),
        origin_type=str(value.get("origin_type") or "uploaded_document"),
        knowledge_candidate_id=_optional_str(value.get("knowledge_candidate_id")),
        prd_version_id=_optional_str(value.get("prd_version_id")),
        content_sha256=_optional_str(value.get("content_sha256")),
    )


def _optional_str(value: object) -> str | None:
    return str(value) if value is not None else None


def _optional_int(value: object) -> int | None:
    return int(value) if value is not None else None
