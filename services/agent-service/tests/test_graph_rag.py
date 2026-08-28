import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from app.agentic_rag import answer_agentic_question
from app.graph_rag import build_risk_chains, lookup_graph, match_question_entities
from app.graph_store import (
    extract_graph_from_text,
    find_paths,
    get_entity_neighborhood,
    get_graph_overview,
    list_entities,
    list_relations,
    rebuild_graph,
)
from app.rag import delete_document, ingest_document
from app.ticket_store import create_ticket


SAMPLE_TEXT = (
    "客户 B 的项目原计划在 2026 年 6 月 20 日交付。\n"
    "有人操作失误导致了项目交付时间推迟到 2026 年 7 月 8 日。\n"
    "延期原因：操作失误。\n"
    "项目负责人是李四。\n"
    "合同中约定，如果延期超过 18 天，需要向客户提交说明书。"
)


class GraphExtractionTests(unittest.TestCase):
    def test_extracts_entities_and_relations_from_sample_text(self) -> None:
        entities, relations = extract_graph_from_text(
            SAMPLE_TEXT, document_id="doc-1", filename="sample.md", chunk_index=0
        )
        names = {(entity.entity_type, entity.name) for entity in entities}
        triples = {(r.source_name, r.relation_type, r.target_name) for r in relations}

        self.assertIn(("customer", "客户B"), names)
        self.assertIn(("project", "客户B项目"), names)
        self.assertIn(("person", "李四"), names)
        self.assertIn(("cause", "操作失误"), names)
        self.assertIn(("date", "2026-06-20"), names)
        self.assertIn(("date", "2026-07-08"), names)
        self.assertIn(("客户B", "委托", "客户B项目"), triples)
        self.assertIn(("客户B项目", "负责人", "李四"), triples)
        self.assertIn(("客户B项目", "延期原因", "操作失误"), triples)
        self.assertIn(("客户B项目", "原计划交付", "2026-06-20"), triples)
        self.assertIn(("客户B项目", "调整后交付", "2026-07-08"), triples)
        self.assertTrue(any(r.relation_type == "约定" for r in relations))
        self.assertTrue(all(r.evidence for r in relations))


class GraphStoreTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.db_patcher = patch("app.database.DB_PATH", Path(self.temp_dir.name) / "graph.sqlite3")
        self.db_patcher.start()
        ingest_document("sample.md", SAMPLE_TEXT)

    def tearDown(self) -> None:
        self.db_patcher.stop()
        self.temp_dir.cleanup()

    def test_ingest_indexes_graph_and_overview_counts(self) -> None:
        overview = get_graph_overview()
        self.assertGreaterEqual(overview["entity_count"], 6)
        self.assertGreaterEqual(overview["relation_count"], 6)
        self.assertEqual(overview["document_count"], 1)
        self.assertIn("customer", overview["entity_types"])

    def test_find_paths_connects_customer_to_owner(self) -> None:
        paths = find_paths("客户B", "李四", max_depth=3)
        self.assertTrue(paths)
        display = " ; ".join(step.display() for step in paths[0])
        self.assertIn("客户B", display)
        self.assertIn("李四", display)

    def test_neighborhood_collects_relations_for_matched_entities(self) -> None:
        relations = get_entity_neighborhood(["客户B"], depth=2)
        triples = {(r.source_name, r.relation_type, r.target_name) for r in relations}
        self.assertIn(("客户B项目", "负责人", "李四"), triples)

    def test_rebuild_links_tickets_into_graph(self) -> None:
        create_ticket("客户B项目延期跟进", "跟进客户B项目的延期恢复计划", status="open")
        rebuild_graph()
        ticket_relations = [r for r in list_relations() if r.source_type == "ticket"]
        self.assertTrue(ticket_relations)
        self.assertTrue(any(r.target_name in {"客户B", "客户B项目"} for r in ticket_relations))

    def test_delete_document_clears_graph(self) -> None:
        document = list_entities(entity_type="customer")[0]
        self.assertEqual(document.name, "客户B")
        documents = ingest_document("extra.md", "客户 C 的项目负责人是王五。")
        delete_document(documents.document_id)
        names = {entity.name for entity in list_entities()}
        self.assertIn("客户B", names)
        self.assertNotIn("客户C", names)


class GraphAgentTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.db_patcher = patch("app.database.DB_PATH", Path(self.temp_dir.name) / "graph.sqlite3")
        self.db_patcher.start()
        ingest_document("sample.md", SAMPLE_TEXT)

    def tearDown(self) -> None:
        self.db_patcher.stop()
        self.temp_dir.cleanup()

    def test_question_entities_are_matched(self) -> None:
        matched = match_question_entities("客户B的项目为什么延期？")
        self.assertIn("客户B", matched)

    def test_lookup_builds_context_and_risk_chains(self) -> None:
        lookup = lookup_graph("客户B的项目为什么延期？", "causal")
        self.assertTrue(lookup.hit)
        self.assertIn("【关系图谱】", lookup.context)
        self.assertTrue(lookup.risk_chains)
        self.assertTrue(build_risk_chains(lookup.relations))

    def test_agentic_answer_includes_graph_paths(self) -> None:
        response = answer_agentic_question("客户B的项目为什么延期？", "local", "keyword")
        summary = response.agent_summary
        self.assertEqual(summary.evidence_status, "passed")
        self.assertIn("Graph Agent", summary.agents)
        self.assertTrue(summary.graph_entities)
        self.assertTrue(summary.graph_paths)
        self.assertIn("【关系图谱】", response.answer)
        self.assertTrue(any(step.name == "graph_lookup" for step in response.trace))

    def test_unrelated_question_skips_graph_context(self) -> None:
        response = answer_agentic_question("火星基地的氧气供应方案是什么？", "local", "keyword")
        self.assertNotIn("【关系图谱】", response.answer)


if __name__ == "__main__":
    unittest.main()
