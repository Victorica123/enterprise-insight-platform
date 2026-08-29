"""A3 回归测试：真实 embedding 接入（含哈希回退）与可选 reranker。

无 fastembed/模型的离线环境必须仍能跑通（回退路径），
因此大多数用例用 patch 模拟模型，不依赖真实下载。
"""
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from app.database import get_embedding_stats, init_db, list_chunk_rows
from app.embeddings import (
    clear_real_embedding_cache,
    cosine_similarity,
    embed_real,
    get_real_embedding_cache_stats,
    get_real_embedding_model,
    is_real_embedding_available,
)
from app.rag import ingest_document
from app.retrievers import (
    Chunk,
    HybridRetriever,
    RetrievalHit,
    RetrievalScope,
    clear_chunk_cache,
    get_chunk_cache_stats,
    get_retriever,
    load_chunks,
)
from app.status_service import build_embedding_status

try:  # pragma: no cover - numpy 随 fastembed 安装，缺失时跳过相关用例
    import numpy as np

    HAS_NUMPY = True
except ImportError:
    HAS_NUMPY = False


class _FloatLike:
    """numpy 缺失时的等价替身：非内置 float，但可被 float() 转换。"""

    __slots__ = ("_value",)

    def __init__(self, value: float) -> None:
        self._value = value

    def __float__(self) -> float:
        return self._value


class FakeEmbeddingModel:
    """返回 numpy float32 的假模型，用于验证类型转换与入库链路。

    只装 requirements.txt 的环境（CI / 全新克隆）没有 numpy，
    降级为 _FloatLike 以保持同一转换路径被覆盖。
    """

    def embed(self, texts: list[str]):
        if HAS_NUMPY:
            return [np.full(8, index / 10.0, dtype=np.float32) for index in range(len(texts))]
        return [[_FloatLike(index / 10.0)] * 8 for index in range(len(texts))]


class RealEmbeddingProviderTests(unittest.TestCase):
    def test_disabled_model_reports_unavailable(self) -> None:
        with patch("app.embeddings._real_model_state", {}), patch("app.embeddings.REAL_EMBEDDING_MODEL", ""):
            self.assertIsNone(get_real_embedding_model())
            self.assertFalse(is_real_embedding_available())

    def test_embed_real_converts_numpy_to_python_floats(self) -> None:
        clear_real_embedding_cache()
        with patch("app.embeddings.get_real_embedding_model", return_value=FakeEmbeddingModel()):
            vectors = embed_real(["a", "b"])
        clear_real_embedding_cache()
        self.assertIsNotNone(vectors)
        assert vectors is not None
        self.assertEqual(len(vectors), 2)
        self.assertTrue(all(isinstance(value, float) for value in vectors[0]))
        self.assertAlmostEqual(vectors[1][0], 0.1)

    def test_embed_real_reuses_digest_keyed_vectors_across_batches(self) -> None:
        class CountingEmbeddingModel:
            def __init__(self) -> None:
                self.calls: list[list[str]] = []

            def embed(self, texts: list[str]):
                self.calls.append(list(texts))
                return [[float(len(text)), 1.0] for text in texts]

        model = CountingEmbeddingModel()
        clear_real_embedding_cache()
        try:
            with patch("app.embeddings.get_real_embedding_model", return_value=model):
                first = embed_real(["重复证据", "新的证据", "重复证据"])
                second = embed_real(["重复证据", "新的证据"])
            self.assertIsNotNone(first)
            self.assertIsNotNone(second)
            assert first is not None and second is not None
            self.assertEqual(len(model.calls), 1)
            self.assertEqual(model.calls[0], ["重复证据", "新的证据"])
            self.assertEqual(first, [first[0], first[1], first[0]])
            self.assertEqual(second, first[:2])
            stats = get_real_embedding_cache_stats()
            self.assertEqual(stats["entries"], 2)
            self.assertEqual(stats["misses"], 2)
            self.assertEqual(stats["hits"], 2)
        finally:
            clear_real_embedding_cache()

    def test_cosine_similarity_dim_mismatch_is_zero(self) -> None:
        self.assertEqual(cosine_similarity([1.0, 0.0], [1.0, 0.0, 0.0]), 0.0)


class CacheObservabilityTests(unittest.TestCase):
    def tearDown(self) -> None:
        clear_real_embedding_cache()
        clear_chunk_cache()

    def test_status_calculates_process_cache_hit_rates(self) -> None:
        status = build_embedding_status(
            {
                "total_chunks": 4,
                "embedded_chunks": 4,
                "missing_chunks": 0,
                "embedded_chunks_v2": 2,
                "missing_chunks_v2": 2,
            },
            embedding_cache_stats={
                "entries": 3, "max_entries": 512, "hits": 6, "misses": 2,
            },
            chunk_cache_stats={
                "entries": 2, "max_entries": 64, "hits": 0, "misses": 0,
            },
        )
        self.assertEqual(status.cache.scope, "process")
        self.assertEqual(status.cache.embedding_vectors.requests, 8)
        self.assertEqual(status.cache.embedding_vectors.hit_rate, 0.75)
        self.assertEqual(status.cache.chunk_snapshots.hit_rate, 0.0)

    def test_chunk_cache_metrics_keep_authorization_scopes_separate(self) -> None:
        clear_chunk_cache()
        team_scope = RetrievalScope(tenant_id="tenant-a")
        personal_scope = RetrievalScope(tenant_id="tenant-a", owner_id="user-a")
        with (
            patch("app.retrievers.database.get_content_revision", return_value=7),
            patch("app.retrievers.database.list_chunk_rows", return_value=[]) as list_rows,
        ):
            load_chunks(team_scope)
            load_chunks(team_scope)
            load_chunks(personal_scope)

        stats = get_chunk_cache_stats()
        self.assertEqual(stats["hits"], 1)
        self.assertEqual(stats["misses"], 2)
        self.assertEqual(stats["entries"], 2)
        self.assertEqual(list_rows.call_count, 2)


class EmbeddingV2StorageTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.db_patcher = patch("app.database.DB_PATH", Path(self.temp_dir.name) / "emb.sqlite3")
        self.db_patcher.start()

    def tearDown(self) -> None:
        self.db_patcher.stop()
        self.temp_dir.cleanup()

    def test_ingest_stores_embedding_v2_when_model_available(self) -> None:
        with patch("app.database.embed_real", return_value=[[float(i)] * 8 for i in range(2)]):
            ingest_document("doc.md", "客户A的项目延期。项目负责人是李四。")
        rows = list_chunk_rows()
        self.assertTrue(all(row["embedding_v2"] for row in rows))
        stats = get_embedding_stats()
        self.assertEqual(stats["embedded_chunks_v2"], len(rows))

    def test_ingest_falls_back_to_hash_only_when_model_missing(self) -> None:
        with patch("app.database.embed_real", return_value=None):
            ingest_document("doc.md", "客户A的项目延期。项目负责人是李四。")
        rows = list_chunk_rows()
        self.assertTrue(all(row["embedding"] for row in rows))
        self.assertTrue(all(not row["embedding_v2"] for row in rows))
        stats = get_embedding_stats()
        self.assertEqual(stats["embedded_chunks_v2"], 0)


class RetrieverFallbackTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.db_patcher = patch("app.database.DB_PATH", Path(self.temp_dir.name) / "retr.sqlite3")
        self.db_patcher.start()
        ingest_document("doc.md", "客户A的项目延期原因是测试环境部署失败。")

    def tearDown(self) -> None:
        self.db_patcher.stop()
        self.temp_dir.cleanup()

    def test_embedding_retriever_uses_hash_fallback_without_model(self) -> None:
        with patch("app.retrievers.is_real_embedding_available", return_value=False):
            result = get_retriever("embedding").search(["项目延期原因"])
        self.assertTrue(result.hits)
        self.assertGreater(max(hit.score for hit in result.hits), 0)

    def test_embedding_retriever_uses_real_vectors_with_model(self) -> None:
        def fake_embed_real(texts):
            return [[float(i)] * 8 for i in range(len(texts))]

        with patch("app.retrievers.is_real_embedding_available", return_value=True), patch(
            "app.retrievers.embed_real", side_effect=fake_embed_real
        ):
            result = get_retriever("embedding").search(["项目延期原因"])
        self.assertTrue(result.hits)


class RerankerTests(unittest.TestCase):
    def test_rerank_head_reorders_by_score(self) -> None:
        hits = [
            RetrievalHit(chunk=Chunk("d", f"f{i}", 0, f"content{i}"), score=90, matched_queries=["q"])
            for i in range(3)
        ]
        retriever = HybridRetriever()
        with patch("app.retrievers.rerank_pairs", return_value=[0.2, 0.9, 0.5]):
            reordered = retriever._rerank_head("question", hits)
        self.assertIsNotNone(reordered)
        assert reordered is not None
        self.assertEqual([hit.chunk.content for hit in reordered[:3]], ["content1", "content2", "content0"])

    def test_rerank_head_returns_none_when_unavailable(self) -> None:
        hits = [RetrievalHit(chunk=Chunk("d", "f", 0, "c"), score=90, matched_queries=["q"])]
        with patch("app.retrievers.rerank_pairs", return_value=None):
            self.assertIsNone(HybridRetriever()._rerank_head("question", hits))


if __name__ == "__main__":
    unittest.main()
