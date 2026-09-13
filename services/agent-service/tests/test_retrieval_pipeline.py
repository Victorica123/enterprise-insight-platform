"""Retrieval decisions must survive evidence selection and reach the answer."""

from __future__ import annotations

import json
import os
import unittest
from contextvars import ContextVar
from threading import Event
from time import perf_counter
from unittest.mock import patch

from app.agentic_rag import answer_agentic_question, hits_to_sources, merge_hits
from app.analysis_evidence import build_analysis_evidence_snapshot
from app.chat_events import ChatCancelled, bind_chat_guard
from app.chat_metrics import infer_standard_outcome
from app.embeddings import rerank_pairs
from app.rag import MAX_SOURCES, answer_question
from app.retrieval_execution import RetrievalChannelExecutor
from app.retrievers import HybridRetriever, RetrievalHit, RetrievalResult, RetrievalScope

from tests.test_chunk_index import _chunk, _index


class RetrievalPipelineTests(unittest.TestCase):
    def setUp(self) -> None:
        self.chunks = [
            _chunk(f"d{index}", f"验收负责人是成员{index}，负责检查交付材料。", "验收负责人" if index == 0 else "")
            for index in range(5)
        ]
        for item in (
            patch("app.retrievers.load_chunk_index", return_value=_index(self.chunks)),
            patch("app.retrievers.is_reranker_configured", return_value=False),
            patch("app.agentic_rag.run_graph_agent"),
            patch.dict(os.environ, {"LLM_ROUTER_ENABLED": "0"}),
        ):
            item.start()
            self.addCleanup(item.stop)

    def channel(self, scores: list[int], *, status: str = "not_used") -> RetrievalResult:
        return RetrievalResult(
            hits=sorted(
                [RetrievalHit(chunk, score, ["验收负责人"])
                 for chunk, score in zip(self.chunks, scores, strict=True)],
                key=lambda hit: hit.score,
                reverse=True,
            ),
            scanned_count=len(self.chunks),
            embedding_status=status,
        )

    def test_rerank_order_reaches_standard_and_agentic_answers(self) -> None:
        # The reranker promotes the last raw-score candidate into the answer.
        # Testing only HybridRetriever would miss the downstream Top-K regression.
        scores = [90, 80, 70, 60, 50]
        for answer in (answer_question, answer_agentic_question):
            with (
                self.subTest(answer=answer.__name__),
                patch("app.retrievers.KeywordRetriever.search_index", return_value=self.channel(scores)),
                patch("app.retrievers.EmbeddingRetriever.search_chunks", return_value=self.channel(scores, status="semantic")),
                patch("app.retrievers.is_reranker_configured", return_value=True),
                patch("app.retrievers.rerank_pairs", return_value=[0.1, 0.2, 0.3, 0.4, 0.9]),
            ):
                response = answer("验收负责人是谁？", "local", "hybrid")
                self.assertEqual([source.document_id for source in response.sources], ["d4", "d3", "d2", "d1"])
                self.assertEqual([source.score for source in response.sources], [50, 60, 70, 80])
                self.assertIn("成员4", response.answer)
                self.assertEqual(len(response.sources), MAX_SOURCES)

    def test_rrf_order_reaches_answer_without_turning_rank_into_relevance(self) -> None:
        with (
            patch("app.retrievers.KeywordRetriever.search_index", return_value=self.channel([100, 40, 0, 0, 0])),
            patch("app.retrievers.EmbeddingRetriever.search_chunks", return_value=self.channel([0, 45, 0, 0, 0], status="semantic")),
        ):
            response = answer_question("验收负责人是谁？", "local", "hybrid")
        self.assertEqual([source.document_id for source in response.sources], ["d1", "d0"])
        self.assertEqual([source.score for source in response.sources], [42, 50])

    def test_weak_channel_matches_do_not_gain_fusion_votes(self) -> None:
        with (
            patch("app.retrievers.KeywordRetriever.search_index", return_value=self.channel([100, 1, 0, 0, 0])),
            patch("app.retrievers.EmbeddingRetriever.search_chunks", return_value=self.channel([0, 1, 0, 0, 0], status="semantic")),
        ):
            result = HybridRetriever().search(["验收负责人"])
        self.assertEqual([hit.chunk.document_id for hit in result.hits], ["d0"])

    def test_semantic_floor_does_not_discard_hash_fallback_matches(self) -> None:
        for status, expected in (("semantic", []), ("hash_model_unavailable", ["d0"])):
            with (
                self.subTest(status=status),
                patch("app.retrievers.KeywordRetriever.search_index", return_value=self.channel([0] * 5)),
                patch("app.retrievers.EmbeddingRetriever.search_chunks", return_value=self.channel([30, 0, 0, 0, 0], status=status)),
            ):
                result = HybridRetriever().search(["验收负责人"])
                self.assertEqual([hit.chunk.document_id for hit in result.hits], expected)

    def test_failed_channel_keeps_healthy_channel_evidence(self) -> None:
        with (
            patch("app.retrievers.KeywordRetriever.search_index", return_value=self.channel([90, 0, 0, 0, 0])),
            patch("app.retrievers.EmbeddingRetriever.search_chunks", side_effect=RuntimeError("private provider detail")),
        ):
            response = answer_question("验收负责人是谁？", "local", "hybrid")
        self.assertEqual([source.document_id for source in response.sources], ["d0"])
        self.assertNotIn("private provider detail", response.model_dump_json())

    def test_keyword_failure_keeps_semantic_evidence_and_fixed_relevance_weights(self) -> None:
        with (
            patch("app.retrievers.KeywordRetriever.search_index", side_effect=RuntimeError("keyword failed")),
            patch("app.retrievers.EmbeddingRetriever.search_chunks", return_value=self.channel([90, 0, 0, 0, 0], status="semantic")),
        ):
            result = HybridRetriever().search(["验收负责人"])
        self.assertEqual([(hit.chunk.document_id, hit.score) for hit in result.hits], [("d0", 45)])
        self.assertEqual([channel.status for channel in result.channels], ["error", "ok"])

    def test_hash_collisions_cannot_displace_strong_keyword_evidence(self) -> None:
        with (
            patch("app.retrievers.KeywordRetriever.search_index", return_value=self.channel([100, 60, 55, 50, 45])),
            patch("app.retrievers.EmbeddingRetriever.search_chunks", return_value=self.channel([1, 95, 90, 85, 80], status="hash_backfill_pending")),
        ):
            response = answer_question("验收负责人是谁？", "local", "hybrid")
        self.assertEqual(response.sources[0].document_id, "d0")
        self.assertEqual(response.sources[0].score, 50)
        self.assertIn("keyword_then_hash", response.model_dump_json())

    def test_filter_boundaries_and_final_budget_counts_are_observable(self) -> None:
        with (
            patch("app.retrievers.KeywordRetriever.search_index", return_value=self.channel([100, 35, 34, 0, 0])),
            patch("app.retrievers.EmbeddingRetriever.search_chunks", return_value=self.channel([0, 0, 0, 45, 44], status="semantic")),
        ):
            result = HybridRetriever().search(["验收负责人"])
        self.assertEqual({hit.chunk.document_id for hit in result.hits}, {"d0", "d1", "d3"})
        self.assertEqual([len(channel.accepted_keys) for channel in result.channels], [2, 1])

        self.chunks = [_chunk(f"d{i}", "验收负责人是成员。" * 30) for i in range(5)]
        for answer in (answer_question, answer_agentic_question):
            with (
                self.subTest(answer=answer.__name__),
                patch("app.retrievers.KeywordRetriever.search_index", return_value=self.channel([90, 80, 70, 60, 50])),
                patch("app.retrievers.EmbeddingRetriever.search_chunks", return_value=self.channel([90, 80, 70, 60, 50], status="semantic")),
                patch.dict(os.environ, {"EVIDENCE_SOURCE_CHAR_BUDGET": "200", "EVIDENCE_TOTAL_CHAR_BUDGET": "400"}),
            ):
                response = answer("验收负责人是谁？", "local", "hybrid")
            self.assertEqual(len(response.sources), 2)
            channels = [step for step in response.trace if step.name.startswith(("retrieval_keyword", "retrieval_embedding"))]
            self.assertEqual(len(channels), 2)
            for step in channels:
                observation = json.loads(step.detail)
                self.assertEqual(observation["raw_count"], 5)
                self.assertEqual(observation["accepted_count"], 5)
                self.assertEqual(observation["selected_count"], 2)
                self.assertGreaterEqual(step.duration_ms, 0)

    def test_no_matches_and_channel_failure_are_not_reported_as_an_empty_library(self) -> None:
        for failed in (False, True):
            with (
                self.subTest(failed=failed),
                patch("app.retrievers.KeywordRetriever.search_index", return_value=self.channel([0] * 5),
                      side_effect=RuntimeError("private") if failed else None),
                patch("app.retrievers.EmbeddingRetriever.search_chunks", return_value=self.channel([30] * 5, status="semantic"),
                      side_effect=RuntimeError("private") if failed else None),
            ):
                response = answer_question("验收负责人是谁？", "local", "hybrid")
            self.assertEqual(response.sources, [])
            self.assertNotIn("请先上传", response.answer)
            step = next(step for step in response.trace if step.name == "retrieve")
            self.assertEqual(step.status, "unavailable" if failed else "no_match")
            self.assertEqual(infer_standard_outcome(response), "refused")

    def test_reranking_cannot_promote_weak_scores_past_the_evidence_gate(self) -> None:
        with (
            patch("app.retrievers.KeywordRetriever.search_index", return_value=self.channel([20] * 5)),
            patch("app.retrievers.EmbeddingRetriever.search_chunks", return_value=self.channel([0] * 5, status="semantic")),
            patch("app.retrievers.is_reranker_configured", return_value=True),
            patch("app.retrievers.rerank_pairs", return_value=[1, 2, 3, 4, 5]),
            patch("app.rag.build_answer") as build,
        ):
            response = answer_question("验收材料有哪些？", "local", "hybrid")
        build.assert_not_called()
        self.assertEqual(response.sources[0].document_id, "d4")
        self.assertTrue(all(source.score == 10 for source in response.sources))
        self.assertEqual(next(step for step in response.trace if step.name == "evidence_check").status, "weak_score")

    def test_analysis_freezes_the_same_final_order_and_original_relevance(self) -> None:
        with (
            patch("app.retrievers.KeywordRetriever.search_index", return_value=self.channel([90, 80, 70, 60, 50])),
            patch("app.retrievers.EmbeddingRetriever.search_chunks", return_value=self.channel([90, 80, 70, 60, 50], status="semantic")),
            patch("app.retrievers.is_reranker_configured", return_value=True),
            patch("app.retrievers.rerank_pairs", return_value=[1, 2, 3, 4, 5]),
            patch("app.analysis_evidence.database.get_content_revision", return_value=7),
        ):
            snapshot = build_analysis_evidence_snapshot("验收负责人", RetrievalScope(tenant_id="test"), limit=2)
        entries = json.loads(snapshot.payload_json)
        self.assertEqual([(entry["rank"], entry["score"]) for entry in entries], [(1, 50), (2, 60)])
        self.assertEqual([chunk.document_id for chunk in snapshot.chunks], ["d4", "d3"])

    def test_invalid_reranker_output_keeps_fusion_order(self) -> None:
        with (
            patch("app.retrievers.KeywordRetriever.search_index", return_value=self.channel([90, 80, 70, 60, 50])),
            patch("app.retrievers.EmbeddingRetriever.search_chunks", return_value=self.channel([90, 80, 70, 60, 50], status="semantic")),
        ):
            baseline = HybridRetriever().search(["验收负责人"])
            for output in ([0.9], [0.1] * 6, [float("nan")] * 5, [float("inf")] * 5):
                with (
                    self.subTest(output=output),
                    patch("app.retrievers.is_reranker_configured", return_value=True),
                    patch("app.retrievers.rerank_pairs", return_value=output),
                ):
                    result = HybridRetriever().search(["验收负责人"])
                    self.assertEqual(result.rerank_status, "unavailable")
                    self.assertEqual(result.hits, baseline.hits)

    def test_retry_merge_preserves_all_query_provenance(self) -> None:
        target = {}
        merge_hits(target, [RetrievalHit(self.chunks[0], 20, ["first query"])])
        merge_hits(target, [RetrievalHit(self.chunks[0], 40, ["retry query"])])
        self.assertEqual(target[self.chunks[0].key].score, 40)
        self.assertEqual(target[self.chunks[0].key].matched_queries, ["first query", "retry query"])

    def test_retry_merge_keeps_best_rank_independent_of_the_strongest_score(self) -> None:
        target = {}
        merge_hits(target, [RetrievalHit(self.chunks[0], 20, ["first"], selection_rank=1),
                            RetrievalHit(self.chunks[1], 90, ["first"], selection_rank=2)])
        merge_hits(target, [RetrievalHit(self.chunks[0], 40, ["retry"], selection_rank=5)])
        self.assertEqual(target[self.chunks[0].key].selection_rank, 1)
        self.assertEqual(target[self.chunks[0].key].score, 40)
        self.assertEqual([source.document_id for source in hits_to_sources(target)], ["d0", "d1"])


class RetrievalDeadlineTests(unittest.TestCase):
    def setUp(self):
        self.executor = RetrievalChannelExecutor(workers=1)
        self.addCleanup(lambda: self.executor.shutdown(wait=True))
        self.release = Event()
        self.addCleanup(self.release.set)
        self.chunk = _chunk("healthy", "验收负责人是张三。")
        for item in (
            patch("app.retrievers.get_retrieval_executor", return_value=self.executor),
            patch("app.retrievers.load_chunk_index", return_value=_index([self.chunk])),
            patch("app.retrievers.KeywordRetriever.search_index", return_value=RetrievalResult([RetrievalHit(self.chunk, 90, ["验收负责人"])], 1)),
            patch("app.retrievers.is_reranker_configured", return_value=False),
            patch.dict(os.environ, {"HYBRID_CHANNEL_TIMEOUT_SECONDS": "0.03", "HYBRID_RERANK_TIMEOUT_SECONDS": "0.03"}),
        ):
            item.start()
            self.addCleanup(item.stop)

    def test_timeout_returns_healthy_evidence_and_saturation_stays_bounded(self):
        started = Event()

        def blocked(*_):
            started.set()
            self.release.wait(2)
            return RetrievalResult([RetrievalHit(_chunk("late", "late evidence"), 100, ["late"])], 1)

        with patch("app.retrievers.EmbeddingRetriever.search_chunks", side_effect=blocked) as embedding:
            begin = perf_counter()
            response = answer_question("验收负责人是谁？", "local", "hybrid")
            self.assertLess(perf_counter() - begin, 0.5)
            self.assertTrue(started.is_set())
            self.assertEqual(response.sources[0].document_id, "healthy")
            step = next(step for step in response.trace if step.name == "retrieval_embedding")
            self.assertEqual(step.status, "timeout")
            frozen = response.model_dump_json()
            for _ in range(5):
                result = HybridRetriever().search(["验收负责人"])
                self.assertEqual([channel.status for channel in result.channels], ["ok", "saturated"])
            self.assertEqual(embedding.call_count, 1)
            self.release.set()
            self.executor.shutdown(wait=True)
            self.assertEqual(response.model_dump_json(), frozen)

    def test_worker_context_and_cancellation_bypass_fallback(self):
        context = ContextVar("test_retrieval_tenant", default="missing")
        token = context.set("tenant-a")
        self.addCleanup(context.reset, token)
        observed = self.executor.run({"keyword": context.get}, 0.5)
        self.assertEqual(observed["keyword"].value, "tenant-a")
        with patch("app.retrievers.EmbeddingRetriever.search_chunks", side_effect=ChatCancelled()):
            with self.assertRaises(ChatCancelled):
                HybridRetriever().search(["验收负责人"])

    def test_cancellation_during_wait_does_not_wait_for_the_channel_deadline(self):
        cancelled = Event()

        def guard():
            if cancelled.is_set():
                raise ChatCancelled()

        def blocked():
            cancelled.set()
            self.release.wait(2)

        with bind_chat_guard(guard):
            begin = perf_counter()
            with self.assertRaises(ChatCancelled):
                self.executor.run({"embedding": blocked}, 1)
            self.assertLess(perf_counter() - begin, 0.5)

    def test_rerank_timeout_retains_fused_order_and_reports_reason(self):
        chunks = [self.chunk, _chunk("second", "验收负责人是李四。")]
        hits = [RetrievalHit(chunks[0], 90, ["query"]), RetrievalHit(chunks[1], 80, ["query"])]

        def blocked(_):
            self.release.wait(2)
            return [0.1, 0.9]

        with (
            patch("app.retrievers.load_chunk_index", return_value=_index(chunks)),
            patch("app.retrievers.KeywordRetriever.search_index", return_value=RetrievalResult(hits, 2)),
            patch("app.retrievers.EmbeddingRetriever.search_chunks", return_value=RetrievalResult(hits, 2, embedding_status="semantic")),
            patch("app.retrievers.is_reranker_configured", return_value=True),
            patch("app.retrievers.rerank_pairs", side_effect=blocked),
        ):
            result = HybridRetriever().search(["验收负责人"])
            self.assertEqual(result.rerank_status, "unavailable")
            self.assertEqual(result.rerank_reason, "timeout")
            self.assertEqual([hit.chunk.document_id for hit in result.hits], ["healthy", "second"])


class RerankerAdapterTests(unittest.TestCase):
    def test_legacy_predict_adapter_still_works(self):
        class LegacyModel:
            def predict(self, _):
                return iter([0.2, 0.8])
        with patch("app.embeddings.get_reranker", return_value=LegacyModel()):
            self.assertEqual(rerank_pairs([("q", "a"), ("q", "b")]), [0.2, 0.8])

    def test_adapter_rejects_wrong_length_and_nonfinite_scores(self) -> None:
        pairs = [("question", "first evidence"), ("question", "second evidence")]
        with patch("app.embeddings.get_reranker") as get_model:
            for scores in ([0.5], [0.1, 0.2, 0.3], [float("nan"), 0.1], [float("inf"), 0.1]):
                with self.subTest(scores=scores):
                    get_model.return_value.rerank_pairs.return_value = scores
                    self.assertIsNone(rerank_pairs(pairs))


if __name__ == "__main__":
    unittest.main()
