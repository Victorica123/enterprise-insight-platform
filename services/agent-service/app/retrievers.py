"""Retrieval channels over authorized chunk snapshots.

``Chunk``/``RetrievalScope``/``load_chunks`` live in ``app.chunk_index`` and the
tokenizer in ``app.text``; they are re-exported here for backwards compatibility
with tests and evaluation scripts that patch ``app.retrievers.*``.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field, replace
from typing import Protocol

from app import database  # noqa: F401 - patch target for tests (app.retrievers.database)
from app.chunk_index import (
    Chunk,
    ChunkIndex,
    RetrievalScope,
    clear_chunk_cache,
    get_chunk_cache_stats,
    load_chunk_index,
    load_chunks,
)
from app.config import get_retriever_mode, get_settings
from app.embeddings import (
    build_embedding,
    cosine_similarity,
    embed_real,
    is_real_embedding_available,
    is_reranker_configured,
    rerank_pairs,
    similarity_to_score,
)
from app.retrieval_execution import get_retrieval_executor
from app.text import (
    CHAR_STOPS,
    STOP_TERMS,
    char_ngrams,
    deduplicate_preserve_order,
    extract_search_terms,
    normalize_text,
    title_term_boost,
    tokenize_words,
)


@dataclass
class RetrievalHit:
    chunk: Chunk
    score: int
    matched_queries: list[str]
    # Final retriever ordering, deliberately separate from absolute relevance.
    # None preserves the legacy keyword/embedding selection policy.
    selection_rank: int | None = None


@dataclass(frozen=True)
class RetrievalChannelObservation:
    name: str
    status: str
    duration_ms: float
    raw_count: int = 0
    accepted_keys: frozenset[tuple[str, int]] = frozenset()
    min_score: float = 0


@dataclass
class RetrievalResult:
    hits: list[RetrievalHit]
    scanned_count: int
    # "disabled": no reranker configured; "applied": head re-ordered;
    # "unavailable": configured but inference failed -> fused order kept, made visible in trace.
    rerank_status: str = "disabled"
    embedding_status: str = "not_used"
    channels: list[RetrievalChannelObservation] = field(default_factory=list)
    rerank_duration_ms: float | None = None
    rerank_reason: str | None = None
    fusion_strategy: str = "score"


# RRF 的平滑常数，取检索文献常用的 60：排名靠前的差异被放大，长尾被压平。
RRF_K = 60

# hybrid 门控分的加权：关键词覆盖率偏召回，向量相似度偏语义，各占一半。
KEYWORD_WEIGHT = 0.5
EMBEDDING_WEIGHT = 0.5

# A3: reranker 只精排头部候选数（控制 CPU 推理延迟）。
RERANK_CANDIDATES = 12


def coverage_to_score(matched: int, total: int) -> int:
    """把"query 词项被命中的比例"映射到 0-100，与向量分同量纲。"""
    if total <= 0:
        return 0

    return round(100 * matched / total)


def reciprocal_rank_fusion(ranked_lists: list[list[tuple[str, int]]]) -> dict[tuple[str, int], float]:
    """RRF：只看排名不看分数，因此对各路检索器的分数量纲不敏感。"""
    fused: dict[tuple[str, int], float] = {}
    for ranked in ranked_lists:
        for rank, key in enumerate(ranked, start=1):
            fused[key] = fused.get(key, 0.0) + 1.0 / (RRF_K + rank)

    return fused


class Retriever(Protocol):
    name: str

    def search(self, queries: list[str], scope: RetrievalScope | None = None) -> RetrievalResult:
        ...


class KeywordRetriever:
    name = "keyword"

    def search(self, queries: list[str], scope: RetrievalScope | None = None) -> RetrievalResult:
        return self.search_index(queries, load_chunk_index(scope))

    def search_index(self, queries: list[str], index: ChunkIndex) -> RetrievalResult:
        query_terms = [(query, extract_search_terms(query)) for query in queries]
        query_terms = [(query, terms) for query, terms in query_terms if terms]
        if not query_terms:
            return RetrievalResult(hits=[], scanned_count=0)

        chunks = index.chunks
        # 只对至少共享一个词项的 chunk 打分（倒排 posting），其余 chunk 分数必为 0。
        all_terms: set[str] = set()
        for _, terms in query_terms:
            all_terms.update(terms)
        candidates = index.candidates(all_terms)

        hits_by_position: dict[int, RetrievalHit] = {}
        for position in candidates:
            chunk = chunks[position]
            chunk_terms = chunk.search_terms()
            scores: list[tuple[str, int]] = []
            for query, terms in query_terms:
                # 归一化为 query 词项覆盖率（0-100），而不是原始交集计数：
                # 原始计数没有上界，长 chunk 天然占优，也无法和向量分放在同一个阈值下比较。
                score = coverage_to_score(len(terms.intersection(chunk_terms)), len(terms))
                if score > 0:
                    scores.append((query, score))
            best_score = max((score for _, score in scores), default=0)
            matched_queries = [query for query, score in scores if score == best_score]
            hits_by_position[position] = RetrievalHit(
                chunk=chunk, score=best_score, matched_queries=matched_queries
            )

        # 未共享任何词项的 chunk 分数必为 0，仍按语料顺序参与稳定排序并落在尾部：
        # 调用方据此区分"没命中"和"知识库为空"，且结果顺序与逐块打分的旧实现完全一致。
        ranked_hits = sorted(
            (
                hits_by_position.get(position)
                or RetrievalHit(chunk=chunk, score=0, matched_queries=[])
                for position, chunk in enumerate(chunks)
            ),
            key=lambda hit: hit.score,
            reverse=True,
        )
        return RetrievalResult(hits=ranked_hits, scanned_count=len(chunks))


class EmbeddingRetriever:
    name = "embedding"

    def search(self, queries: list[str], scope: RetrievalScope | None = None) -> RetrievalResult:
        query_texts = [query for query in queries if query.strip()]
        if not query_texts:
            return RetrievalResult(hits=[], scanned_count=0)

        return self.search_chunks(query_texts, list(load_chunk_index(scope).chunks))

    def search_chunks(self, query_texts: list[str], chunks: list[Chunk]) -> RetrievalResult:
        # Never infer a corpus of missing vectors on a user request. A partial
        # v2 index uses one consistent hash space until background backfill finishes.
        if is_real_embedding_available():
            if all(chunk.embedding_v2 for chunk in chunks):
                real_hits = self._search_real(query_texts, chunks)
                if real_hits is not None:
                    real_hits.embedding_status = "semantic"
                    return real_hits
                status = "hash_query_failed"
            else:
                status = "hash_backfill_pending"
        else:
            status = "hash_model_unavailable"
        result = self._search_hash(query_texts, chunks)
        result.embedding_status = status
        return result

    def _search_real(self, query_texts: list[str], chunks: list[Chunk]) -> RetrievalResult | None:
        query_vectors = embed_real(query_texts)
        if query_vectors is None:
            return None
        chunk_vectors = [chunk.embedding_v2 for chunk in chunks]

        hits: list[RetrievalHit] = []
        for index, chunk in enumerate(chunks):
            chunk_vector = chunk_vectors[index]
            if chunk_vector is None:
                continue
            scores = [
                (query, cosine_similarity(query_vector, chunk_vector))
                for query, query_vector in zip(query_texts, query_vectors, strict=True)
            ]
            best_similarity = max((score for _, score in scores), default=0.0)
            score = similarity_to_score(best_similarity)
            matched_queries = [
                query
                for query, query_score in scores
                if similarity_to_score(query_score) == score and score > 0
            ]
            hits.append(
                RetrievalHit(
                    chunk=chunk,
                    score=score,
                    matched_queries=matched_queries,
                )
            )

        ranked_hits = sorted(hits, key=lambda hit: hit.score, reverse=True)
        return RetrievalResult(hits=ranked_hits, scanned_count=len(chunks))

    def _search_hash(self, query_texts: list[str], chunks: list[Chunk]) -> RetrievalResult:
        query_vectors = [(query, build_embedding(query)) for query in query_texts]
        hits: list[RetrievalHit] = []
        for chunk in chunks:
            chunk_vector = chunk.embedding or build_embedding(chunk.content)
            scores = [
                (query, cosine_similarity(query_vector, chunk_vector))
                for query, query_vector in query_vectors
            ]
            best_similarity = max((score for _, score in scores), default=0.0)
            score = similarity_to_score(best_similarity)
            matched_queries = [
                query
                for query, query_score in scores
                if similarity_to_score(query_score) == score and score > 0
            ]
            hits.append(
                RetrievalHit(
                    chunk=chunk,
                    score=score,
                    matched_queries=matched_queries,
                )
            )

        ranked_hits = sorted(hits, key=lambda hit: hit.score, reverse=True)
        return RetrievalResult(hits=ranked_hits, scanned_count=len(chunks))


class HybridRetriever:
    """关键词 + 向量融合。

    排序用 RRF：两路分数即使量纲不同也能安全合并，且不会被某一路的绝对值支配。
    门控分用加权归一化分：证据门控需要的是"到底有多相关"这种绝对量，
    而 RRF 只表达相对排名（语料里只有一个 chunk 时它照样排第一）。
    """

    name = "hybrid"

    def search(self, queries: list[str], scope: RetrievalScope | None = None) -> RetrievalResult:
        # Authorization precedes dispatch; both channels see the same snapshot.
        index = load_chunk_index(scope)
        query_texts = [query for query in queries if query.strip()]
        if not index.chunks or not query_texts:
            return RetrievalResult(hits=[], scanned_count=len(index.chunks))
        settings = get_settings().hybrid_retrieval
        executor = get_retrieval_executor()
        executions = executor.run({
            "keyword": lambda: KeywordRetriever().search_index(queries, index),
            "embedding": lambda: EmbeddingRetriever().search_chunks(query_texts, list(index.chunks)),
        }, settings.channel_timeout_seconds)
        keyword_result = executions["keyword"].value or RetrievalResult([], 0)
        embedding_result = executions["embedding"].value or RetrievalResult([], 0)
        embedding_status = (embedding_result.embedding_status if executions["embedding"].status == "ok"
                            else executions["embedding"].status)
        thresholds = {
            "keyword": max((hit.score for hit in keyword_result.hits), default=0) * settings.keyword_min_ratio,
            "embedding": settings.semantic_min_score if embedding_status == "semantic" else settings.hash_min_score,
        }

        chunks: dict[tuple[str, int], Chunk] = {}
        keyword_scores: dict[tuple[str, int], int] = {}
        embedding_scores: dict[tuple[str, int], int] = {}
        matched: dict[tuple[str, int], list[str]] = {}
        ranked_lists: list[list[tuple[str, int]]] = []
        channels: list[RetrievalChannelObservation] = []

        for name, result, scores in (("keyword", keyword_result, keyword_scores),
                                     ("embedding", embedding_result, embedding_scores)):
            # Weak matches cannot acquire an extra RRF vote or inflate the gate.
            accepted = [hit for hit in result.hits if hit.score > 0 and hit.score >= thresholds[name]]
            if name == "keyword":
                accepted.sort(key=lambda hit: hit.score + title_term_boost(query_texts[0], hit.chunk.title), reverse=True)
            ranked_lists.append([hit.chunk.key for hit in accepted])
            channels.append(RetrievalChannelObservation(
                name=name, status=executions[name].status, duration_ms=executions[name].duration_ms,
                raw_count=len(result.hits), accepted_keys=frozenset(hit.chunk.key for hit in accepted),
                min_score=thresholds[name],
            ))
            for hit in accepted:
                key = (hit.chunk.document_id, hit.chunk.chunk_index)
                chunks.setdefault(key, hit.chunk)
                scores[key] = hit.score
                matched[key] = deduplicate_preserve_order(matched.get(key, []) + hit.matched_queries)

        hits = [
            RetrievalHit(
                chunk=chunk,
                score=round(
                    KEYWORD_WEIGHT * keyword_scores.get(key, 0)
                    + EMBEDDING_WEIGHT * embedding_scores.get(key, 0)
                ),
                matched_queries=matched.get(key, []),
            )
            for key, chunk in chunks.items()
        ]
        fusion_strategy = "rrf"
        if embedding_status.startswith("hash_"):
            # Hash n-grams are another lexical approximation, not an independent
            # semantic vote. Keep accepted keyword ranks, then append hash-only
            # candidates; collisions must not displace direct textual evidence.
            fallback_order = dict.fromkeys(ranked_lists[0] + ranked_lists[1])
            by_key = {hit.chunk.key: hit for hit in hits}
            ranked_hits = [by_key[key] for key in fallback_order]
            fusion_strategy = "keyword_then_hash"
        else:
            # With a real semantic channel, RRF resolves different score scales;
            # exact keyword coverage remains the deterministic tie-breaker.
            fused = reciprocal_rank_fusion(ranked_lists)
            ranked_hits = sorted(
                hits,
                key=lambda hit: (fused.get(hit.chunk.key, 0.0), keyword_scores.get(hit.chunk.key, 0), hit.score),
                reverse=True,
            )

        # Optional reranker changes candidate order, never evidence confidence.
        # 默认关闭（RERANKER_MODEL 为空）；启用后对延迟预算负责（见 embeddings.py 注释）。
        rerank_status = "disabled"
        rerank_duration_ms = None
        rerank_reason = None
        if len(ranked_hits) > 1 and queries and is_reranker_configured():
            execution = executor.run({"rerank": lambda: self._rerank_head(queries[0], ranked_hits)},
                                     settings.rerank_timeout_seconds)["rerank"]
            rerank_duration_ms = execution.duration_ms
            if execution.value is not None:
                ranked_hits = execution.value
                rerank_status = "applied"
            else:
                # 精排失败不伪造分数：保留融合榜，并让调用方在 trace 中标明降级。
                rerank_status = "unavailable"
                rerank_reason = "invalid_or_unavailable" if execution.status == "ok" else execution.status

        return RetrievalResult(
            hits=[replace(hit, selection_rank=rank) for rank, hit in enumerate(ranked_hits, start=1)],
            scanned_count=len(index.chunks),
            rerank_status=rerank_status,
            embedding_status=embedding_status,
            channels=channels,
            rerank_duration_ms=rerank_duration_ms,
            rerank_reason=rerank_reason,
            fusion_strategy=fusion_strategy,
        )

    def _rerank_head(
        self, question: str, ranked_hits: list[RetrievalHit]
    ) -> list[RetrievalHit] | None:
        head = ranked_hits[:RERANK_CANDIDATES]
        scores = rerank_pairs([(question, hit.chunk.content) for hit in head])
        if scores is None or len(scores) != len(head) or not all(math.isfinite(score) for score in scores):
            return None
        order = sorted(range(len(head)), key=lambda i: scores[i], reverse=True)
        return [head[i] for i in order] + ranked_hits[RERANK_CANDIDATES:]


def get_retriever(mode: str | None = None) -> Retriever:
    mode = mode or get_retriever_mode()
    if mode == "embedding":
        return EmbeddingRetriever()

    if mode == "hybrid":
        return HybridRetriever()

    return KeywordRetriever()


__all__ = [
    "CHAR_STOPS",
    "Chunk",
    "EMBEDDING_WEIGHT",
    "EmbeddingRetriever",
    "HybridRetriever",
    "KEYWORD_WEIGHT",
    "KeywordRetriever",
    "RERANK_CANDIDATES",
    "RRF_K",
    "RetrievalHit",
    "RetrievalResult",
    "RetrievalScope",
    "Retriever",
    "STOP_TERMS",
    "char_ngrams",
    "clear_chunk_cache",
    "coverage_to_score",
    "deduplicate_preserve_order",
    "extract_search_terms",
    "get_chunk_cache_stats",
    "get_retriever",
    "load_chunks",
    "normalize_text",
    "reciprocal_rank_fusion",
    "tokenize_words",
]
