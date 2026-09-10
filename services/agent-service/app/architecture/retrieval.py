"""Retrieval and evidence boundary (检索与证据中心).

Authorization-aware scope construction, hybrid retrieval, graph enrichment and
evidence snapshots are exposed here as one application boundary.  The existing
retriever/store modules remain the persistence adapters.
"""

from app.analysis_evidence import build_analysis_evidence_snapshot
from app.evidence_provenance import EvidenceProvenanceError, validate_and_normalize_evidence
from app.graph_rag import GraphLookup, lookup_graph, question_wants_graph
from app.retrievers import (
    Chunk,
    EmbeddingRetriever,
    HybridRetriever,
    KeywordRetriever,
    RetrievalHit,
    RetrievalResult,
    RetrievalScope,
    Retriever,
    get_chunk_cache_stats,
    get_retriever,
)


class EvidenceRetrievalService:
    """Small façade that keeps retrieval and evidence authorization together."""

    def snapshot(self, objective: str, scope: RetrievalScope):
        return build_analysis_evidence_snapshot(objective, scope)

    def search(self, queries: list[str], scope: RetrievalScope, mode: str | None = None):
        return get_retriever(mode).search(queries, scope)


__all__ = [
    "Chunk",
    "EmbeddingRetriever",
    "EvidenceProvenanceError",
    "EvidenceRetrievalService",
    "GraphLookup",
    "HybridRetriever",
    "KeywordRetriever",
    "RetrievalHit",
    "RetrievalResult",
    "RetrievalScope",
    "Retriever",
    "build_analysis_evidence_snapshot",
    "get_chunk_cache_stats",
    "lookup_graph",
    "question_wants_graph",
    "validate_and_normalize_evidence",
]
