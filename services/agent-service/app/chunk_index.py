"""Authorized chunk snapshots with precomputed terms and a posting index.

Retrievers used to re-tokenize every chunk on every request.  The snapshot now
computes search terms once per cache entry and keeps a term -> chunk posting
list, so keyword scoring only touches chunks that share at least one term with
the query.  Cache entries are keyed by the *tenant* content revision, so a write
in one workspace no longer evicts every other workspace's snapshot.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from functools import lru_cache

from app import database
from app.embeddings import embedding_from_json
from app.text import extract_search_terms


@dataclass
class Chunk:
    document_id: str
    filename: str
    chunk_index: int
    content: str
    embedding: list[float] | None = None
    embedding_v2: list[float] | None = None  # A3: 真实语义 embedding（512 维）
    title: str = ""  # A4: 块标题（最近的 markdown 标题）
    tenant_id: str = "legacy"
    owner_id: str = "legacy"
    source_type: str = "document"
    asset_id: str | None = None
    segment_id: str | None = None
    start_ms: int | None = None
    end_ms: int | None = None
    speaker: str | None = None
    origin_type: str = "uploaded_document"
    knowledge_candidate_id: str | None = None
    prd_version_id: str | None = None
    content_sha256: str | None = None
    knowledge_version_id: str | None = None
    knowledge_version_number: int | None = None
    knowledge_lifecycle_status: str | None = None
    superseded_by_document_id: str | None = None
    # Precomputed once per snapshot; empty means "compute lazily" for ad-hoc chunks.
    terms: frozenset[str] = field(default_factory=frozenset, repr=False, compare=False)

    @property
    def key(self) -> tuple[str, int]:
        return (self.document_id, self.chunk_index)

    def search_terms(self) -> frozenset[str]:
        if self.terms:
            return self.terms
        searchable = f"{self.title} {self.content}" if self.title else self.content
        return frozenset(extract_search_terms(searchable))


@dataclass(frozen=True)
class RetrievalScope:
    """Authorization filter applied before any evidence reaches a model."""

    tenant_id: str
    owner_id: str | None = None
    asset_ids: tuple[str, ...] = ()


@dataclass(frozen=True)
class ChunkIndex:
    chunks: tuple[Chunk, ...]
    postings: dict[str, tuple[int, ...]]

    def candidates(self, terms: set[str]) -> set[int]:
        found: set[int] = set()
        for term in terms:
            posting = self.postings.get(term)
            if posting:
                found.update(posting)
        return found


def load_chunk_index(scope: RetrievalScope | None = None) -> ChunkIndex:
    tenant_id = scope.tenant_id if scope else None
    owner_id = scope.owner_id if scope else None
    asset_ids = scope.asset_ids if scope else ()
    revision = database.get_content_revision(tenant_id)
    return _load_chunk_index_cached(
        database.database_identity(), revision, tenant_id, owner_id, asset_ids
    )


def load_chunks(scope: RetrievalScope | None = None) -> list[Chunk]:
    return list(load_chunk_index(scope).chunks)


@lru_cache(maxsize=64)
def _load_chunk_index_cached(
    db_path: str,
    revision: int,
    tenant_id: str | None,
    owner_id: str | None,
    asset_ids: tuple[str, ...],
) -> ChunkIndex:
    # Both values intentionally participate in the cache key. The revision is
    # stored in the selected database, so writes from another process invalidate this cache too.
    del db_path, revision
    chunks: list[Chunk] = []
    postings: dict[str, list[int]] = {}
    for row in database.list_chunk_rows(
        tenant_id=tenant_id,
        owner_id=owner_id,
        asset_ids=asset_ids,
    ):
        chunk = _row_to_chunk(row)
        position = len(chunks)
        chunks.append(chunk)
        for term in chunk.terms:
            postings.setdefault(term, []).append(position)
    return ChunkIndex(
        chunks=tuple(chunks),
        postings={term: tuple(positions) for term, positions in postings.items()},
    )


def _row_to_chunk(row) -> Chunk:
    keys = row.keys()
    source_type = row["source_type"] if "source_type" in keys else "document"
    try:
        metadata = json.loads(row["metadata_json"] or "{}") if "metadata_json" in keys else {}
    except (TypeError, json.JSONDecodeError):
        metadata = {}
    if not isinstance(metadata, dict):
        metadata = {}
    title = row["chunk_title"] if "chunk_title" in keys else ""
    content = row["content"]
    is_knowledge = source_type == "knowledge"
    return Chunk(
        document_id=row["document_id"],
        filename=row["filename"],
        chunk_index=row["chunk_index"],
        content=content,
        embedding=embedding_from_json(row["embedding"]),
        embedding_v2=embedding_from_json(row["embedding_v2"]) if "embedding_v2" in keys else None,
        title=title or "",
        tenant_id=row["tenant_id"] if "tenant_id" in keys else "legacy",
        owner_id=row["owner_id"] if "owner_id" in keys else "legacy",
        source_type=source_type,
        asset_id=row["asset_id"] if "asset_id" in keys else None,
        segment_id=row["segment_id"] if "segment_id" in keys else None,
        start_ms=row["start_ms"] if "start_ms" in keys else None,
        end_ms=row["end_ms"] if "end_ms" in keys else None,
        speaker=row["speaker"] if "speaker" in keys else None,
        origin_type=(
            "approved_knowledge" if is_knowledge
            else "media_transcript" if source_type == "video"
            else "uploaded_document"
        ),
        knowledge_candidate_id=row["external_id"] if is_knowledge and "external_id" in keys else None,
        prd_version_id=metadata.get("prd_version_id"),
        content_sha256=row["payload_sha256"] if is_knowledge and "payload_sha256" in keys else None,
        knowledge_version_id=metadata.get("knowledge_version_id") if is_knowledge else None,
        knowledge_version_number=metadata.get("knowledge_version_number") if is_knowledge else None,
        knowledge_lifecycle_status=(
            row["lifecycle_status"] if is_knowledge and "lifecycle_status" in keys else None
        ),
        superseded_by_document_id=(
            row["superseded_by_document_id"]
            if is_knowledge and "superseded_by_document_id" in keys
            else None
        ),
        terms=frozenset(extract_search_terms(f"{title} {content}" if title else content)),
    )


def clear_chunk_cache() -> None:
    _load_chunk_index_cached.cache_clear()


def get_chunk_cache_stats() -> dict[str, int]:
    info = _load_chunk_index_cached.cache_info()
    return {
        "entries": info.currsize,
        "max_entries": info.maxsize or 0,
        "hits": info.hits,
        "misses": info.misses,
    }


__all__ = [
    "Chunk",
    "ChunkIndex",
    "RetrievalScope",
    "clear_chunk_cache",
    "get_chunk_cache_stats",
    "load_chunk_index",
    "load_chunks",
]
