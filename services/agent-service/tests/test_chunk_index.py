"""Chunk snapshot index: precomputed terms, posting lists, rerank status and per-tenant revision."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from app import database
from app.chunk_index import (
    Chunk,
    ChunkIndex,
    RetrievalScope,
    clear_chunk_cache,
    get_chunk_cache_stats,
    load_chunks,
)
from app.rag import describe_rerank, ingest_document, rerank_trace_steps
from app.retrievers import (
    HybridRetriever,
    KeywordRetriever,
    RetrievalHit,
    RetrievalResult,
    coverage_to_score,
)
from app.text import extract_search_terms


def _chunk(document_id: str, content: str, title: str = "") -> Chunk:
    searchable = f"{title} {content}" if title else content
    return Chunk(
        document_id=document_id,
        filename=f"{document_id}.md",
        chunk_index=0,
        content=content,
        title=title,
        terms=frozenset(extract_search_terms(searchable)),
    )


def _index(chunks: list[Chunk]) -> ChunkIndex:
    postings: dict[str, list[int]] = {}
    for position, chunk in enumerate(chunks):
        for term in chunk.terms:
            postings.setdefault(term, []).append(position)
    return ChunkIndex(
        chunks=tuple(chunks),
        postings={term: tuple(positions) for term, positions in postings.items()},
    )


def _brute_force(queries: list[str], chunks: list[Chunk]) -> list[RetrievalHit]:
    """The pre-index algorithm: tokenize and score every chunk, stable sort by score."""
    query_terms = [(query, extract_search_terms(query)) for query in queries]
    query_terms = [(query, terms) for query, terms in query_terms if terms]
    hits: list[RetrievalHit] = []
    for chunk in chunks:
        searchable = f"{chunk.title} {chunk.content}" if chunk.title else chunk.content
        chunk_terms = extract_search_terms(searchable)
        scores = []
        for query, terms in query_terms:
            score = coverage_to_score(len(terms & chunk_terms), len(terms))
            if score > 0:
                scores.append((query, score))
        best = max((score for _, score in scores), default=0)
        hits.append(
            RetrievalHit(
                chunk=chunk,
                score=best,
                matched_queries=[query for query, score in scores if score == best],
            )
        )
    return sorted(hits, key=lambda hit: hit.score, reverse=True)


def _shape(hits: list[RetrievalHit]) -> list[tuple[tuple[str, int], int, list[str]]]:
    return [(hit.chunk.key, hit.score, hit.matched_queries) for hit in hits]


CORPUS = [
    _chunk("d1", "客户A的项目延期，原因是需求变更。", title="项目周报"),
    _chunk("d2", "退款时效 PRD 要求 48 小时内处理。"),
    _chunk("d3", "团队建设活动安排在周五。"),
    _chunk("d4", "客户A要求补充验收标准。"),
    _chunk("d5", "hello world release notes"),
    _chunk("d6", "项目延期风险评估。"),
]


class KeywordPostingTests(unittest.TestCase):
    def setUp(self) -> None:
        self.index = _index(CORPUS)

    def test_search_index_matches_brute_force_order(self) -> None:
        for queries in (
            ["项目延期原因"],
            ["客户A", "验收标准"],
            ["release notes"],
            ["完全不相关的词汇xyz"],
        ):
            with self.subTest(queries=queries):
                result = KeywordRetriever().search_index(queries, self.index)
                self.assertEqual(result.scanned_count, len(CORPUS))
                self.assertEqual(_shape(result.hits), _shape(_brute_force(queries, CORPUS)))

    def test_candidates_skip_chunks_without_shared_terms(self) -> None:
        candidates = self.index.candidates(extract_search_terms("退款时效"))
        self.assertIn(1, candidates)
        self.assertNotIn(2, candidates)
        self.assertNotIn(4, candidates)

    def test_ad_hoc_chunk_computes_terms_lazily(self) -> None:
        chunk = Chunk("d", "f.md", 0, "客户A延期", title="周报")
        self.assertEqual(chunk.terms, frozenset())
        self.assertEqual(chunk.search_terms(), frozenset(extract_search_terms("周报 客户A延期")))

    def test_blank_queries_scan_nothing(self) -> None:
        result = KeywordRetriever().search_index(["", "   "], self.index)
        self.assertEqual(result.hits, [])
        self.assertEqual(result.scanned_count, 0)


class HybridRerankStatusTests(unittest.TestCase):
    def setUp(self) -> None:
        self.patches = [
            patch("app.retrievers.load_chunk_index", return_value=_index(CORPUS)),
            patch("app.retrievers.is_real_embedding_available", return_value=False),
        ]
        for item in self.patches:
            item.start()
            self.addCleanup(item.stop)

    def test_status_is_disabled_without_reranker(self) -> None:
        with patch("app.retrievers.is_reranker_configured", return_value=False):
            result = HybridRetriever().search(["项目延期原因"])
        self.assertEqual(result.rerank_status, "disabled")
        self.assertEqual(result.hits[0].chunk.document_id, "d1")

    def test_failed_reranker_keeps_fused_order_and_is_visible(self) -> None:
        with patch("app.retrievers.is_reranker_configured", return_value=False):
            baseline = HybridRetriever().search(["项目延期原因"])
        with (
            patch("app.retrievers.is_reranker_configured", return_value=True),
            patch("app.retrievers.rerank_pairs", return_value=None),
        ):
            degraded = HybridRetriever().search(["项目延期原因"])
        self.assertEqual(degraded.rerank_status, "unavailable")
        self.assertEqual(_shape(degraded.hits), _shape(baseline.hits))

    def test_applied_reranker_reorders_head(self) -> None:
        def reversed_scores(pairs: list[tuple[str, str]]) -> list[float]:
            return [float(index) for index in range(len(pairs))]

        with (
            patch("app.retrievers.is_reranker_configured", return_value=True),
            patch("app.retrievers.rerank_pairs", side_effect=reversed_scores),
        ):
            result = HybridRetriever().search(["项目延期原因"])
        self.assertEqual(result.rerank_status, "applied")
        self.assertNotEqual(result.hits[0].chunk.document_id, "d1")

    def test_trace_helpers_only_speak_when_rerank_is_configured(self) -> None:
        disabled = RetrievalResult(hits=[], scanned_count=0)
        self.assertEqual(describe_rerank(disabled), "")
        self.assertEqual(rerank_trace_steps(disabled), [])

        unavailable = RetrievalResult(hits=[], scanned_count=0, rerank_status="unavailable")
        self.assertIn("精排不可用", describe_rerank(unavailable))
        steps = rerank_trace_steps(unavailable)
        self.assertEqual([(step.name, step.status) for step in steps], [("rerank_skipped", "degraded")])


class TenantRevisionTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp_dir.cleanup)
        patcher = patch("app.database.DB_PATH", Path(self.temp_dir.name) / "chunks.sqlite3")
        patcher.start()
        self.addCleanup(patcher.stop)
        clear_chunk_cache()
        self.addCleanup(clear_chunk_cache)

    @staticmethod
    def _ingest(tenant: str, filename: str, content: str) -> None:
        ingest_document(
            filename, content, tenant_id=tenant, owner_id=f"user-{tenant}", index_graph=False
        )

    def test_tenant_write_keeps_other_tenant_snapshot(self) -> None:
        self._ingest("tenant-a", "a.md", "客户A项目延期")
        self._ingest("tenant-b", "b.md", "客户B验收标准")
        clear_chunk_cache()
        scope_a = RetrievalScope(tenant_id="tenant-a")
        scope_b = RetrievalScope(tenant_id="tenant-b")
        load_chunks(scope_a)
        load_chunks(scope_b)
        self.assertEqual(get_chunk_cache_stats()["misses"], 2)

        self._ingest("tenant-a", "a2.md", "客户A新的需求变更")

        self.assertEqual(len(load_chunks(scope_b)), 1)
        self.assertEqual(get_chunk_cache_stats()["hits"], 1)
        self.assertEqual(len(load_chunks(scope_a)), 2)
        self.assertEqual(get_chunk_cache_stats()["misses"], 3)

    def test_global_bump_invalidates_tenant_snapshots(self) -> None:
        self._ingest("tenant-b", "b.md", "客户B验收标准")
        clear_chunk_cache()
        scope_b = RetrievalScope(tenant_id="tenant-b")
        load_chunks(scope_b)
        with database.connect() as conn:
            database.bump_content_revision(conn)
        load_chunks(scope_b)
        self.assertEqual(get_chunk_cache_stats()["misses"], 2)
        self.assertEqual(get_chunk_cache_stats()["hits"], 0)

    def test_unscoped_snapshot_follows_tenant_writes(self) -> None:
        self._ingest("tenant-a", "a.md", "客户A项目延期")
        clear_chunk_cache()
        self.assertEqual(len(load_chunks()), 1)
        self._ingest("tenant-a", "a2.md", "客户A新的需求变更")
        self.assertEqual(len(load_chunks()), 2)
        self.assertEqual(get_chunk_cache_stats()["misses"], 2)

    def test_unknown_tenant_reads_global_revision(self) -> None:
        self._ingest("tenant-a", "a.md", "客户A项目延期")
        self.assertEqual(
            database.get_content_revision("never-written"), database.get_content_revision()
        )
        self.assertEqual(
            database.get_content_revision("tenant-a"), database.get_content_revision()
        )


if __name__ == "__main__":
    unittest.main()
