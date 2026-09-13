import os
import sqlite3
import subprocess
import sys
import tempfile
import unittest
from contextlib import closing
from pathlib import Path
from unittest.mock import patch

from app import database, schema


class SchemaStartupTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.path = Path(temp.name) / "upgrade.sqlite3"
        self.enterContext(patch.object(database, "DB_PATH", self.path))
        self.enterContext(patch.object(database, "_INITIALIZED_DB_PATH", None))
        self.enterContext(patch.dict(os.environ, {"AGENT_DATABASE_URL": "", "APP_ENV": "test"}))

    def test_legacy_rows_survive_upgrade_and_repeated_startup(self):
        with closing(sqlite3.connect(self.path)) as conn, conn:
            conn.execute("create table documents (id text primary key, filename text not null, created_at text)")
            conn.execute("create table chunks (id text primary key, document_id text, filename text, chunk_index integer, content text, created_at text)")
            conn.execute("insert into documents values ('old-doc', 'old.md', '2020-01-01')")
            conn.execute("insert into chunks values ('old-chunk', 'old-doc', 'old.md', 0, '客户A的原始事实', '2020-01-01')")
        database.init_db()
        database._INITIALIZED_DB_PATH = None  # Another process/restart must respect the ledger.
        database.init_db()
        with database.connect() as conn:
            row = conn.execute("select content, tenant_id, owner_id, embedding_blob from chunks").fetchone()
            self.assertEqual(tuple(row), ("客户A的原始事实", "legacy", "legacy", None))
            self.assertEqual(conn.execute("select count(*) from schema_migrations").fetchone()[0], len(schema.MIGRATIONS))
            self.assertEqual(conn.execute("pragma quick_check").fetchone()[0], "ok")

    def test_failed_sqlite_migration_rolls_back_schema_data_and_ledger(self):
        database.init_db()

        def broken(conn):
            conn.execute("create table failed_upgrade (id integer)")
            conn.execute("update system_meta set value = 99 where key = 'content_revision'")
            raise RuntimeError("injected migration failure")

        database._INITIALIZED_DB_PATH = None
        last_version = schema.MIGRATIONS[-1][0]
        with patch.object(schema, "MIGRATIONS", (*schema.MIGRATIONS, (last_version + 1, "failure", broken))):
            with self.assertRaisesRegex(RuntimeError, "injected"):
                database.init_db()
        self.assertIsNone(database._INITIALIZED_DB_PATH)
        database.init_db()
        with database.connect() as conn:
            self.assertIsNone(conn.execute("select name from sqlite_master where name = 'failed_upgrade'").fetchone())
            self.assertEqual(conn.execute("select value from system_meta where key = 'content_revision'").fetchone()[0], 0)
            self.assertEqual(conn.execute("select max(version) from schema_migrations").fetchone()[0], last_version)

    def test_newer_database_rejects_an_older_application(self):
        database.init_db()
        with database.connect() as conn:
            conn.execute("insert into schema_migrations(version, name) values (999, 'future')")
        database._INITIALIZED_DB_PATH = None
        with self.assertRaisesRegex(RuntimeError, "newer or differs"):
            database.init_db()

    def test_two_processes_can_initialize_the_same_database(self):
        environment = {**os.environ, "AGENT_DATABASE_PATH": str(self.path), "AGENT_DATABASE_URL": ""}
        directory = Path(__file__).resolve().parents[1]
        processes = [subprocess.Popen(
            [sys.executable, "-c", "from app.database import init_db; init_db()"],
            cwd=directory, env=environment, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
        ) for _ in range(2)]
        for process in processes:
            self.addCleanup(lambda p=process: p.kill() if p.poll() is None else None)
        for process in processes:
            _, error = process.communicate(timeout=30)
            self.assertEqual(process.returncode, 0, error.decode(errors="replace"))
        with database.connect() as conn:
            self.assertEqual(conn.execute("select count(*) from schema_migrations").fetchone()[0], len(schema.MIGRATIONS))

    def test_mysql_lock_is_released_after_a_failure(self):
        class Connection:
            def __init__(self):
                self.sql = []
                self.rolled_back = False

            def execute(self, sql, params=()):
                self.sql.append(sql)
                if "create table" in sql:
                    raise RuntimeError("injected DDL failure")
                return self

            def fetchone(self):
                return (1,)

            def rollback(self):
                self.rolled_back = True

        conn = Connection()
        with self.assertRaisesRegex(RuntimeError, "injected"):
            schema.apply_migrations(conn, mysql=True, identity="mysql://localhost/test")
        self.assertTrue(conn.rolled_back)
        self.assertIn("release_lock", conn.sql[-1])
