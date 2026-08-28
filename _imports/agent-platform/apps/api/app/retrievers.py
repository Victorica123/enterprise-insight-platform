from dataclasses import dataclass
from functools import lru_cache
from typing import Protocol

from app import database
from app.config import get_retriever_mode
from app.embeddings import (
    build_embedding,
    cosine_similarity,
    embed_real,
    embedding_from_json,
    is_real_embedding_available,
    rerank_pairs,
    similarity_to_score,
)


@dataclass
class Chunk:
    document_id: str
    filename: str
    chunk_index: int
    content: str
    embedding: list[float] | None = None
    embedding_v2: list[float] | None = None  # A3: 真实语义 embedding（512 维）
    title: str = ""  # A4: 块标题（最近的 markdown 标题）


@dataclass
class RetrievalHit:
    chunk: Chunk
    score: int
    matched_queries: list[str]


@dataclass
class RetrievalResult:
    hits: list[RetrievalHit]
    scanned_count: int


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

    def search(self, queries: list[str]) -> RetrievalResult:
        ...


class KeywordRetriever:
    name = "keyword"

    def search(self, queries: list[str]) -> RetrievalResult:
        query_terms = [(query, extract_search_terms(query)) for query in queries]
        query_terms = [(query, terms) for query, terms in query_terms if terms]
        if not query_terms:
            return RetrievalResult(hits=[], scanned_count=0)

        chunks = load_chunks()
        hits: list[RetrievalHit] = []
        for chunk in chunks:
            # A4: 标题词项并入 chunk 词项——"违约责任条款"这类标题关键词才能命中
            searchable = f"{chunk.title} {chunk.content}" if chunk.title else chunk.content
            chunk_terms = extract_search_terms(searchable)
            scores: list[tuple[str, int]] = []
            for query, terms in query_terms:
                # 归一化为 query 词项覆盖率（0-100），而不是原始交集计数：
                # 原始计数没有上界，长 chunk 天然占优，也无法和向量分放在同一个阈值下比较。
                score = coverage_to_score(len(terms.intersection(chunk_terms)), len(terms))
                if score > 0:
                    scores.append((query, score))

            best_score = max((score for _, score in scores), default=0)
            matched_queries = [query for query, score in scores if score == best_score]
            hits.append(
                RetrievalHit(
                    chunk=chunk,
                    score=best_score,
                    matched_queries=matched_queries,
                )
            )

        ranked_hits = sorted(hits, key=lambda hit: hit.score, reverse=True)
        return RetrievalResult(hits=ranked_hits, scanned_count=len(chunks))


class EmbeddingRetriever:
    name = "embedding"

    def search(self, queries: list[str]) -> RetrievalResult:
        query_texts = [query for query in queries if query.strip()]
        if not query_texts:
            return RetrievalResult(hits=[], scanned_count=0)

        chunks = load_chunks()

        # A3: 真实语义 embedding 优先（query 与缺失 chunk 向量各批量推理一次）；
        # 模型不可用或推理失败时整体回退哈希 n-gram 版。
        if is_real_embedding_available():
            real_hits = self._search_real(query_texts, chunks)
            if real_hits is not None:
                return real_hits

        return self._search_hash(query_texts, chunks)

    def _search_real(self, query_texts: list[str], chunks: list[Chunk]) -> RetrievalResult | None:
        query_vectors = embed_real(query_texts)
        if query_vectors is None:
            return None
        chunk_vectors: list[list[float] | None] = []
        missing_indexes: list[int] = []
        for index, chunk in enumerate(chunks):
            if chunk.embedding_v2:
                chunk_vectors.append(chunk.embedding_v2)
            else:
                chunk_vectors.append(None)
                missing_indexes.append(index)
        if missing_indexes:
            generated = embed_real([chunks[i].content for i in missing_indexes])
            if generated is None:
                return None
            for offset, index in enumerate(missing_indexes):
                chunk_vectors[index] = generated[offset]

        hits: list[RetrievalHit] = []
        for index, chunk in enumerate(chunks):
            chunk_vector = chunk_vectors[index]
            if chunk_vector is None:
                continue
            scores = [
                (query, cosine_similarity(query_vector, chunk_vector))
                for query, query_vector in zip(query_texts, query_vectors)
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

    def search(self, queries: list[str]) -> RetrievalResult:
        keyword_result = KeywordRetriever().search(queries)
        embedding_result = EmbeddingRetriever().search(queries)

        chunks: dict[tuple[str, int], Chunk] = {}
        keyword_scores: dict[tuple[str, int], int] = {}
        embedding_scores: dict[tuple[str, int], int] = {}
        matched: dict[tuple[str, int], list[str]] = {}

        for result, scores in ((keyword_result, keyword_scores), (embedding_result, embedding_scores)):
            for hit in result.hits:
                key = (hit.chunk.document_id, hit.chunk.chunk_index)
                chunks.setdefault(key, hit.chunk)
                scores[key] = hit.score
                matched[key] = deduplicate_preserve_order(matched.get(key, []) + hit.matched_queries)

        # 只让真正命中的 chunk 参与排名，否则零分文档也会白拿一份 RRF 权重。
        fused = reciprocal_rank_fusion(
            [
                [
                    (hit.chunk.document_id, hit.chunk.chunk_index)
                    for hit in result.hits
                    if hit.score > 0
                ]
                for result in (keyword_result, embedding_result)
            ]
        )

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
        ranked_hits = sorted(
            hits,
            key=lambda hit: (
                fused.get((hit.chunk.document_id, hit.chunk.chunk_index), 0.0),
                hit.score,
            ),
            reverse=True,
        )

        # A3: 可选 reranker 精排——只重排 RRF 候选头部，门控分保持不变。
        # 默认关闭（RERANKER_MODEL 为空）；启用后对延迟预算负责（见 embeddings.py 注释）。
        if len(ranked_hits) > 1 and queries:
            reranked = self._rerank_head(queries[0], ranked_hits)
            if reranked is not None:
                ranked_hits = reranked

        return RetrievalResult(
            hits=ranked_hits,
            scanned_count=max(keyword_result.scanned_count, embedding_result.scanned_count),
        )

    def _rerank_head(
        self, question: str, ranked_hits: list[RetrievalHit]
    ) -> list[RetrievalHit] | None:
        head = ranked_hits[:RERANK_CANDIDATES]
        scores = rerank_pairs([(question, hit.chunk.content) for hit in head])
        if scores is None:
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


def load_chunks() -> list[Chunk]:
    revision = database.get_content_revision()
    return list(_load_chunks_cached(str(database.DB_PATH.resolve()), revision))


@lru_cache(maxsize=16)
def _load_chunks_cached(db_path: str, revision: int) -> tuple[Chunk, ...]:
    # Both values intentionally participate in the cache key. The revision is
    # stored in SQLite, so writes from another process invalidate this cache too.
    del db_path, revision
    return tuple(
        Chunk(
            document_id=row["document_id"],
            filename=row["filename"],
            chunk_index=row["chunk_index"],
            content=row["content"],
            embedding=embedding_from_json(row["embedding"]),
            embedding_v2=embedding_from_json(row["embedding_v2"]) if "embedding_v2" in row.keys() else None,
            title=row["chunk_title"] if "chunk_title" in row.keys() else "",
        )
        for row in database.list_chunk_rows()
    )


def clear_chunk_cache() -> None:
    _load_chunks_cached.cache_clear()


def deduplicate_preserve_order(values: list[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for value in values:
        normalized = value.strip()
        if normalized and normalized not in seen:
            seen.add(normalized)
            result.append(normalized)

    return result


def extract_search_terms(text: str) -> set[str]:
    normalized = normalize_text(text)
    terms = tokenize_words(normalized)

    compact = "".join(normalized.split())
    terms.update(char_ngrams(compact, size=1))
    terms.update(char_ngrams(compact, size=2))

    return {term for term in terms if term not in STOP_TERMS and term not in CHAR_STOPS}


# A2: 停用词——去掉只贡献噪声、不贡献主题的通用词/字，
# 减少"配置""情况"这类通用词制造的字面重合虚高分。
STOP_TERMS = {
    "什么", "怎么", "如何", "哪些", "这个", "那个", "一下",
    "情况", "问题", "为什么", "请问", "多少", "哪里", "方案", "时候",
}

CHAR_STOPS = {
    "的", "了", "是", "在", "与", "和", "及", "或", "吗", "呢",
    "啊", "请", "把", "被", "对", "从", "向", "就", "都", "也",
    "还", "会", "个", "有", "要", "为",
}


def normalize_text(text: str) -> str:
    separators = " \n\t\r,.;:!?，。！？；：、（）()[]{}<>\"'“”‘’"
    normalized = text.lower()
    for separator in separators:
        normalized = normalized.replace(separator, " ")

    return normalized


def tokenize_words(text: str) -> set[str]:
    return {term for term in text.split(" ") if term}


def char_ngrams(text: str, size: int) -> set[str]:
    if size <= 0 or len(text) < size:
        return set()

    return {text[index : index + size] for index in range(len(text) - size + 1)}
