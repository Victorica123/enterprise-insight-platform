from __future__ import annotations

import sqlite3
import tempfile
import unittest
from contextlib import closing
from pathlib import Path
from unittest.mock import Mock, patch

from app import database
from app.architecture.orchestration import ConversationInput, ConversationOrchestrator
from app.chunk_index import Chunk, RetrievalScope, clear_chunk_cache, load_chunks
from app.embedding_maintenance import backfill_embeddings_once
from app.evidence_sources import expand_parent_sources
from app.models import Source
from app.retrievers import EmbeddingRetriever
from app.topic_routing import TopicCandidate, assess_topic_candidates, route_authorized_topics
from app.vector_codec import decode_vector, encode_vector


class VectorCodecTests(unittest.TestCase):
    def test_binary_and_legacy_are_readable_with_corruption_fallback(self):
        values = [0.25, -0.5, 1.0]
        self.assertEqual(decode_vector(encode_vector(values)), values)
        self.assertEqual(decode_vector(None, "[0.25,-0.5,1]"), values)
        self.assertEqual(decode_vector(b"EIV1broken", "[1,2]"), [1, 2])
        self.assertIsNone(decode_vector(b"unknown"))
        with self.assertRaises(ValueError):
            encode_vector([float("nan")])

    def test_missing_vectors_never_infer_documents_on_request(self):
        chunks = [Chunk("a", "a.md", 0, "secret document", embedding=[1.0, 0.0]),
                  Chunk("b", "b.md", 0, "another document", embedding=[0.0, 1.0], embedding_v2=[1.0, 0.0])]
        with patch("app.retrievers.is_real_embedding_available", return_value=True), patch("app.retrievers.embed_real") as model:
            result = EmbeddingRetriever().search_chunks(["question"], chunks)
        model.assert_not_called()
        self.assertEqual(result.embedding_status, "hash_backfill_pending")
        self.assertEqual(len(result.hits), 2)

    def test_complete_index_only_embeds_query(self):
        chunk = Chunk("a", "a.md", 0, "document", embedding_v2=[1.0, 0.0])
        with patch("app.retrievers.is_real_embedding_available", return_value=True), patch("app.retrievers.embed_real", return_value=[[1.0, 0.0]]) as model:
            result = EmbeddingRetriever().search_chunks(["question"], [chunk])
        model.assert_called_once_with(["question"])
        self.assertEqual(result.embedding_status, "semantic")


class RetrievalStorageTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.patcher = patch("app.database.DB_PATH", Path(self.temp.name) / "retrieval.sqlite3")
        self.patcher.start()
        self.addCleanup(self.patcher.stop)
        clear_chunk_cache()
        self.addCleanup(clear_chunk_cache)
        self.model = patch("app.database.embed_real", return_value=None)
        self.model.start()
        self.addCleanup(self.model.stop)

    def insert(self, identifier="doc-a", tenant="a", owner="alice", title="客户A / 进度", chunks=None):
        database.insert_document(identifier, identifier + ".md", chunks or [(title, "客户A项目负责人是李四。")], tenant_id=tenant, owner_id=owner)

    def test_additive_migration_and_legacy_cache_read(self):
        self.insert()
        with database.connect() as conn:
            conn.execute("update chunks set embedding_blob = null")
        self.assertTrue(load_chunks(RetrievalScope("a", "alice"))[0].embedding)
        with patch("app.embedding_maintenance.embed_real", return_value=None):
            self.assertEqual(backfill_embeddings_once(), 1)
        row = database.list_chunk_rows()[0]
        self.assertTrue(row["embedding_blob"].startswith(b"EIV1"))
        self.assertTrue(row["embedding"])  # Rollback readers retain their JSON column.

    def test_backfill_is_bounded_and_only_invalidates_changed_tenant(self):
        self.insert()
        self.insert("doc-b", "b", "bob")
        revisions = {tenant: database.get_content_revision(tenant) for tenant in ("a", "b")}
        with patch("app.embedding_maintenance.embed_real", return_value=[[1.0, 0.0]]) as model:
            self.assertEqual(backfill_embeddings_once(batch_size=1), 1)
        self.assertEqual(len(model.call_args.args[0]), 1)
        self.assertGreater(database.get_content_revision("a"), revisions["a"])
        self.assertEqual(database.get_content_revision("b"), revisions["b"])

    def test_backfill_inference_holds_no_database_write_transaction(self):
        self.insert()
        def infer(_texts):
            with closing(sqlite3.connect(database.DB_PATH, timeout=0.1)) as other:
                other.execute("begin immediate")
                other.rollback()
            return [[1.0, 0.0]]
        with patch("app.embedding_maintenance.embed_real", side_effect=infer):
            self.assertEqual(backfill_embeddings_once(), 1)

    def test_parent_expansion_preserves_scope_and_section(self):
        self.insert(chunks=[("客户A / 进度", "原因是环境故障。"), ("客户A / 进度", "修复负责人李四。"), ("合同", "不应合并。")])
        self.insert("private", "a", "bob", chunks=[("客户A / 进度", "另一位用户的私有信息。")])
        chunk = load_chunks(RetrievalScope("a", "alice"))[0]
        source = Source(document_id=chunk.document_id, filename=chunk.filename, chunk_index=0, score=90, content=chunk.content, parent_key=chunk.parent_key)
        expanded = expand_parent_sources([source], RetrievalScope("a", "alice"))[0]
        self.assertIn("修复负责人李四", expanded.content)
        self.assertNotIn("不应合并", expanded.content)
        self.assertNotIn("私有信息", expanded.content)
        self.assertEqual(expanded.chunk_indices, [0, 1])

    def test_parent_expansion_keeps_video_location_and_char_cap(self):
        video = Source(source_type="video", document_id="v", filename="v.mp4", chunk_index=0, score=90, content="video", asset_id="v", segment_id="s", start_ms=10, end_ms=20)
        self.assertEqual(expand_parent_sources([video]), [video])
        self.insert(chunks=[("同节", "甲" * 1600), ("同节", "乙" * 1600)])
        chunk = load_chunks(RetrievalScope("a", "alice"))[0]
        source = Source(document_id=chunk.document_id, filename=chunk.filename, chunk_index=0, score=90, content=chunk.content, parent_key=chunk.parent_key)
        self.assertEqual(len(expand_parent_sources([source], RetrievalScope("a", "alice"))[0].content), 1600)

    def test_ambiguity_only_uses_authorized_competing_topics(self):
        self.insert()
        self.insert("doc-b", title="客户B", chunks=[("客户B", "客户B项目负责人是王五。")])
        self.insert("private", "secret", "bob", title="客户SECRET")
        decision = route_authorized_topics("项目负责人是谁？", RetrievalScope("a", "alice"))
        self.assertIsNotNone(decision.question)
        self.assertNotIn("secret", decision.question.lower())
        self.assertIsNone(route_authorized_topics("客户A项目负责人是谁？", RetrievalScope("a", "alice")))
        self.assertIsNone(route_authorized_topics("分别介绍所有项目负责人", RetrievalScope("a", "alice")))
        standard, agentic = Mock(), Mock()
        response = ConversationOrchestrator(standard_handler=standard, agentic_handler=agentic).answer(ConversationInput(
            question="项目负责人是谁？", workflow_mode="agentic", answer_mode="local", retriever_mode="keyword", retrieval_scope=RetrievalScope("a", "alice")))
        standard.assert_not_called()
        agentic.assert_not_called()
        self.assertEqual(response.agent_summary.execution_mode, "clarify")


class RelativeConfidenceTests(unittest.TestCase):
    def test_single_dominant_close_and_empty_candidates(self):
        self.assertIsNone(assess_topic_candidates([TopicCandidate("A", 1)]).question)
        self.assertIsNone(assess_topic_candidates([TopicCandidate("A", 90), TopicCandidate("B", 10)]).question)
        ambiguous = assess_topic_candidates([TopicCandidate("A", 50), TopicCandidate("B", 49)])
        self.assertAlmostEqual(ambiguous.confidence, 50 / 104)
        self.assertIsNotNone(ambiguous.question)
        self.assertEqual(assess_topic_candidates([]).reason, "no_candidates")


if __name__ == "__main__":
    unittest.main()
