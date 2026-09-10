"""Server-side validation for evidence references used by governed writes."""
from __future__ import annotations

import json
import sqlite3
from typing import Any


class EvidenceProvenanceError(ValueError):
    """Raised when a client/model-supplied evidence reference is not persisted evidence."""


def validate_and_normalize_evidence(
    conn: sqlite3.Connection,
    evidence: list[dict[str, object]],
    *,
    tenant_id: str,
    owner_id: str | None = None,
) -> list[dict[str, object]]:
    """Resolve evidence against active chunks and return server-owned references.

    The caller may use tenant-wide scope for team workspaces (``owner_id=None``)
    or tenant+owner scope for personal workspaces.  All display/location fields
    are read from the database; only the excerpt is accepted from the request
    after it is proven to be contained in the persisted chunk text.
    """
    if not evidence:
        raise EvidenceProvenanceError("At least one persisted evidence reference is required.")

    normalized: list[dict[str, object]] = []
    for index, item in enumerate(evidence):
        source_type = _required_text(item, "source_type", index)
        if source_type not in {"document", "video"}:
            raise EvidenceProvenanceError(f"Evidence {index} has an unsupported source type.")
        document_id = _required_text(item, "document_id", index)
        filename = _required_text(item, "filename", index)
        chunk_index = _non_negative_int(item.get("chunk_index"), "chunk_index", index)
        excerpt = _required_text(item, "excerpt", index)

        predicates = [
            "chunks.document_id = ?",
            "chunks.chunk_index = ?",
            "chunks.tenant_id = ?",
            "documents.tenant_id = ?",
            "documents.lifecycle_status = 'ACTIVE'",
        ]
        parameters: list[object] = [document_id, chunk_index, tenant_id, tenant_id]
        if owner_id is not None:
            predicates.append("chunks.owner_id = ?")
            parameters.append(owner_id)
        row = conn.execute(
            f"""
            select chunks.document_id, chunks.filename, chunks.chunk_index, chunks.content,
                   chunks.tenant_id, chunks.owner_id, chunks.source_type, chunks.asset_id,
                   chunks.segment_id, chunks.start_ms, chunks.end_ms, chunks.speaker,
                   documents.metadata_json
            from chunks
            join documents on documents.id = chunks.document_id
            where {' and '.join(predicates)}
            """,
            parameters,
        ).fetchone()
        if row is None:
            raise EvidenceProvenanceError(
                f"Evidence {index} does not resolve to an active chunk in the authorized scope."
            )
        if row["filename"] != filename:
            raise EvidenceProvenanceError(f"Evidence {index} filename does not match persisted provenance.")
        persisted_type = "video" if row["source_type"] == "video" else "document"
        if persisted_type != source_type:
            raise EvidenceProvenanceError(f"Evidence {index} source type does not match persisted provenance.")

        if _compact(excerpt) not in _compact(row["content"]):
            raise EvidenceProvenanceError(f"Evidence {index} excerpt is not contained in the persisted chunk.")

        if source_type == "video":
            asset_id = _required_text(item, "asset_id", index)
            segment_id = _required_text(item, "segment_id", index)
            start_ms = _non_negative_int(item.get("start_ms"), "start_ms", index)
            end_ms = _non_negative_int(item.get("end_ms"), "end_ms", index)
            if end_ms < start_ms:
                raise EvidenceProvenanceError(f"Evidence {index} has an invalid time range.")
            if (
                row["asset_id"] != asset_id
                or row["segment_id"] != segment_id
                or row["start_ms"] != start_ms
                or row["end_ms"] != end_ms
            ):
                raise EvidenceProvenanceError(f"Evidence {index} video location does not match persisted provenance.")
            duration_ms = _document_duration(row["metadata_json"])
            if duration_ms is not None and end_ms > duration_ms:
                raise EvidenceProvenanceError(f"Evidence {index} exceeds the persisted video duration.")
        else:
            # A document reference cannot smuggle video coordinates into the
            # governed artifact; the normalized reference owns these as null.
            asset_id = segment_id = None
            start_ms = end_ms = None

        normalized.append({
            "source_type": source_type,
            "document_id": row["document_id"],
            "filename": row["filename"],
            "chunk_index": int(row["chunk_index"]),
            "excerpt": excerpt.strip(),
            "asset_id": asset_id,
            "segment_id": segment_id,
            "start_ms": start_ms,
            "end_ms": end_ms,
            "speaker": row["speaker"] if source_type == "video" else None,
        })
    return normalized


def _required_text(item: dict[str, object], name: str, index: int) -> str:
    value = item.get(name)
    if not isinstance(value, str) or not value.strip():
        raise EvidenceProvenanceError(f"Evidence {index} requires a non-empty {name}.")
    return value.strip()


def _non_negative_int(value: object, name: str, index: int) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise EvidenceProvenanceError(f"Evidence {index} requires a non-negative integer {name}.")
    return value


def _compact(value: object) -> str:
    return " ".join(str(value or "").split())


def _document_duration(raw: object) -> int | None:
    try:
        metadata: Any = json.loads(raw or "{}")
    except (TypeError, json.JSONDecodeError):
        return None
    value = metadata.get("duration_ms") if isinstance(metadata, dict) else None
    return value if isinstance(value, int) and not isinstance(value, bool) and value >= 0 else None
