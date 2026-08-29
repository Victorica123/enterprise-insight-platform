import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from app import database
from app.graph_store import get_graph_overview, init_graph_store, list_entities
from app.rag import ingest_document
from app.ticket_store import create_ticket, list_tickets, record_tool_call, list_tool_call_logs


class LegacyStoreTenantIsolationTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.db_patch = patch("app.database.DB_PATH", Path(self.temp.name) / "tenant.sqlite3")
        self.db_patch.start()
        database._INITIALIZED_DB_PATH = None

    def tearDown(self) -> None:
        self.db_patch.stop()
        database._INITIALIZED_DB_PATH = None
        self.temp.cleanup()

    def test_tickets_and_tool_audit_do_not_cross_owner_or_tenant(self) -> None:
        create_ticket("A1", "tenant A user 1", tenant_id="tenant-a", owner_id="user-1")
        create_ticket("A2", "tenant A user 2", tenant_id="tenant-a", owner_id="user-2")
        create_ticket("B1", "tenant B user 1", tenant_id="tenant-b", owner_id="user-1")

        visible = list_tickets(tenant_id="tenant-a", owner_id="user-1")
        self.assertEqual([item.title for item in visible], ["A1"])

        record_tool_call(
            tool_name="query_tickets", operation="read", requires_approval=False,
            status="succeeded", actor_role="operator", input_payload={},
            tenant_id="tenant-a", owner_id="user-1", actor_user="user-1",
        )
        record_tool_call(
            tool_name="query_tickets", operation="read", requires_approval=False,
            status="succeeded", actor_role="operator", input_payload={},
            tenant_id="tenant-b", owner_id="user-1", actor_user="user-1",
        )
        logs = list_tool_call_logs(tenant_id="tenant-a")
        self.assertEqual(len(logs), 1)
        self.assertEqual(logs[0]["tenant_id"], "tenant-a")

    def test_graph_identity_and_rebuild_are_scoped(self) -> None:
        ingest_document(
            "a.md", "客户 A 的项目负责人是李四。",
            tenant_id="tenant-a", owner_id="user-1",
        )
        ingest_document(
            "b.md", "客户 B 的项目负责人是王五。",
            tenant_id="tenant-b", owner_id="user-2",
        )

        names_a = {
            item.name for item in list_entities(tenant_id="tenant-a", owner_id="user-1")
        }
        names_b = {
            item.name for item in list_entities(tenant_id="tenant-b", owner_id="user-2")
        }
        self.assertIn("客户A", names_a)
        self.assertNotIn("客户B", names_a)
        self.assertIn("客户B", names_b)
        self.assertEqual(
            get_graph_overview(tenant_id="tenant-a", owner_id="user-1")["document_count"],
            1,
        )

    def test_legacy_global_graph_is_migrated_to_isolated_legacy_scope(self) -> None:
        database.init_db()
        with database.connect() as conn:
            conn.execute(
                """
                create table graph_entities (
                    entity_id text primary key, name text not null, entity_type text not null,
                    mention_count integer not null, document_ids text not null, created_at text not null,
                    unique(name, entity_type)
                )
                """
            )
            conn.execute(
                """
                create table graph_relations (
                    relation_id text primary key, source_name text not null, source_type text not null,
                    relation_type text not null, target_name text not null, target_type text not null,
                    evidence text not null, document_id text not null, filename text not null,
                    chunk_index integer not null, created_at text not null,
                    unique(source_name, relation_type, target_name, document_id, chunk_index)
                )
                """
            )
            conn.execute("create table graph_meta (key text primary key, value text not null)")
            conn.execute(
                "insert into graph_entities values ('e1', '客户旧', 'customer', 1, '[\"doc-old\"]', '2026-01-01')"
            )
            conn.execute(
                "insert into graph_meta values ('last_built_at', '2026-01-01')"
            )

        init_graph_store()

        self.assertEqual([item.name for item in list_entities()], ["客户旧"])
        self.assertEqual(get_graph_overview()["built_at"], "2026-01-01")
        self.assertEqual(
            list_entities(tenant_id="tenant-a", owner_id="user-1"),
            [],
        )


if __name__ == "__main__":
    unittest.main()
