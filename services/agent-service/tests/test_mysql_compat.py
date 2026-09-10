import os
import unittest
from unittest.mock import patch

from app.database import validate_database_configuration
from app.db_compat import CompatRow, translate_mysql_sql


class MySqlCompatibilityTests(unittest.TestCase):
    def test_translates_placeholders_and_upsert(self):
        sql, parameters, begin = translate_mysql_sql(
            """
            insert into graph_meta (tenant_id, owner_id, key, value) values (?, ?, ?, ?)
            on conflict(tenant_id, owner_id, key) do update set value = excluded.value
            """,
            ("tenant", "owner", "revision", "2"),
        )

        self.assertFalse(begin)
        self.assertIn("`key`", sql)
        self.assertIn("on duplicate key update", sql.lower())
        self.assertIn("values(value)", sql.lower())
        self.assertEqual(4, sql.count("%s"))
        self.assertEqual(("tenant", "owner", "revision", "2"), parameters)

    def test_translates_schema_introspection_and_transaction(self):
        sql, parameters, begin = translate_mysql_sql("pragma table_info(documents)")
        self.assertIn("information_schema.columns", sql)
        self.assertEqual(("documents",), parameters)
        self.assertFalse(begin)

        sql, parameters, begin = translate_mysql_sql("begin immediate")
        self.assertEqual("", sql)
        self.assertEqual((), parameters)
        self.assertTrue(begin)

    def test_translates_mysql_safe_ddl_and_partial_unique_index(self):
        ddl, _, _ = translate_mysql_sql(
            """
            create table if not exists documents (
                id text primary key,
                external_id text not null default '',
                metadata_json text not null default '{}',
                created_at text not null default current_timestamp
            )
            """
        )
        self.assertIn("id varchar(191) primary key", ddl)
        self.assertIn("external_id varchar(191) null", ddl)
        self.assertIn("metadata_json longtext not null default ('{}')", ddl)
        self.assertIn("default (concat(replace(utc_timestamp(), ' ', 'T'), '+00:00'))", ddl)

        index, _, _ = translate_mysql_sql(
            """create unique index if not exists uk_documents_external_version
            on documents(tenant_id, source_type, external_id, source_version)
            where external_id != ''"""
        )
        self.assertNotIn("if not exists", index.lower())
        self.assertNotIn("where external_id", index.lower())

        pending_index, _, _ = translate_mysql_sql(
            "create unique index if not exists uk_knowledge_lifecycle_pending "
            "on knowledge_lifecycle_requests(pending_candidate_id)"
        )
        self.assertNotIn("if not exists", pending_index.lower())
        self.assertIn("(pending_candidate_id)", pending_index)

        altered, _, _ = translate_mysql_sql(
            "alter table documents add column external_id text not null default ''"
        )
        self.assertIn("external_id varchar(191) null", altered)

    def test_production_mysql_requirement_fails_closed(self):
        with patch.dict(
            os.environ,
            {
                "APP_ENV": "production",
                "AGENT_REQUIRE_MYSQL": "true",
                "AGENT_DATABASE_URL": "",
            },
            clear=False,
        ):
            with self.assertRaisesRegex(RuntimeError, "requires AGENT_DATABASE_URL"):
                validate_database_configuration()

        with patch.dict(
            os.environ,
            {
                "APP_ENV": "production",
                "AGENT_REQUIRE_MYSQL": "true",
                "AGENT_DATABASE_URL": "mysql+pymysql://user:secret@mysql/agent_platform",
            },
            clear=False,
        ):
            validate_database_configuration()

    def test_empty_external_id_becomes_null_for_mysql_unique_semantics(self):
        _, parameters, _ = translate_mysql_sql(
            "insert into documents (id, external_id, filename) values (?, ?, ?)",
            ("doc-1", "", "brief.md"),
        )
        self.assertEqual(("doc-1", None, "brief.md"), parameters)

    def test_compat_row_supports_name_and_index_access(self):
        row = CompatRow(["id", "name"], [7, "example"])
        self.assertEqual(7, row[0])
        self.assertEqual("example", row["name"])
        self.assertEqual(["id", "name"], list(row.keys()))


if __name__ == "__main__":
    unittest.main()
