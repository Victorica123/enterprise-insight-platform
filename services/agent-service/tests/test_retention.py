import os
import tempfile
import unittest
from datetime import UTC, datetime
from pathlib import Path
from unittest.mock import patch

from app import database
from app.analysis_store import init_analysis_store
from app.graph_store import init_graph_store
from app.retention import run_retention_once
from app.ticket_store import init_ticket_store


class RetentionTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.db_patch = patch("app.database.DB_PATH", Path(self.temp.name) / "retention.sqlite3")
        self.env_patch = patch.dict(
            os.environ,
            {
                "RETENTION_ENABLED": "1",
                "RETENTION_TRANSCRIPT_DAYS": "180",
                "RETENTION_AUDIT_DAYS": "365",
                "RETENTION_BATCH_SIZE": "50",
            },
        )
        self.db_patch.start()
        self.env_patch.start()
        database._INITIALIZED_DB_PATH = None
        database.init_db()
        init_ticket_store()
        init_graph_store()
        init_analysis_store()

    def tearDown(self):
        self.env_patch.stop()
        self.db_patch.stop()
        database._INITIALIZED_DB_PATH = None
        self.temp.cleanup()

    def test_expires_video_evidence_and_old_audit_but_keeps_recent_rows(self):
        database.insert_document(
            "video-old",
            "old.mp4",
            [("", "old transcript")],
            tenant_id="tenant-a",
            owner_id="user-a",
            source_type="video",
            external_id="asset-old",
        )
        database.insert_document(
            "video-new",
            "new.mp4",
            [("", "new transcript")],
            tenant_id="tenant-a",
            owner_id="user-a",
            source_type="video",
            external_id="asset-new",
        )
        with database.connect() as conn:
            conn.execute("update documents set created_at = ? where id = ?", ("2020-01-01T00:00:00+00:00", "video-old"))
            metric_values = (
                "agentic", "local", "hybrid", "fact", "simple", 1, 1,
                "passed", "passed", 1, "answered", "completed", 10.0, 10,
            )
            conn.execute(
                """insert into chat_metrics (
                    workflow_mode, answer_mode, retriever_mode, intent, complexity,
                    retrieval_rounds, query_count, evidence_status, citation_status,
                    source_count, outcome, answer_status, latency_ms, answer_chars, created_at
                ) values (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (*metric_values, "2020-01-01T00:00:00+00:00"),
            )
            conn.execute(
                """insert into chat_metrics (
                    workflow_mode, answer_mode, retriever_mode, intent, complexity,
                    retrieval_rounds, query_count, evidence_status, citation_status,
                    source_count, outcome, answer_status, latency_ms, answer_chars, created_at
                ) values (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (*metric_values, "2026-09-01T00:00:00+00:00"),
            )

        result = run_retention_once(datetime(2026, 9, 4, tzinfo=UTC))

        self.assertEqual(1, result["video_documents"])
        self.assertEqual(1, result["audit_records"])
        with database.connect() as conn:
            self.assertIsNone(conn.execute("select id from documents where id = ?", ("video-old",)).fetchone())
            self.assertIsNotNone(conn.execute("select id from documents where id = ?", ("video-new",)).fetchone())
            self.assertEqual(1, conn.execute("select count(*) as total from chat_metrics").fetchone()["total"])


if __name__ == "__main__":
    unittest.main()
