from __future__ import annotations

from contextlib import closing
import sqlite3
import sys
import tempfile
from pathlib import Path
import unittest
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[3]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts import local_data  # noqa: E402


class LocalDataBackupTests(unittest.TestCase):
    def test_backup_verify_and_force_restore_round_trip(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            runtime = root / "runtime"
            backups = root / "backups"
            database = runtime / "agent" / "knowledge_base.sqlite3"
            database.parent.mkdir(parents=True)
            with closing(sqlite3.connect(database)) as connection:
                connection.execute("create table smoke(value text)")
                connection.execute("insert into smoke values ('before')")
                connection.commit()

            media = runtime / "media" / "storage" / "sample.txt"
            media.parent.mkdir(parents=True)
            media.write_text("original", encoding="utf-8")

            with (
                patch.object(local_data, "RUNTIME", runtime),
                patch.object(local_data, "BACKUPS", backups),
            ):
                archive = local_data.write_backup(backups / "roundtrip.zip")
                manifest = local_data.verify_backup(archive)
                media.write_text("mutated", encoding="utf-8")
                restored, safety = local_data.restore_backup(archive, force=True)

                self.assertEqual(restored, runtime)
                self.assertEqual(media.read_text(encoding="utf-8"), "original")
                self.assertEqual(len(manifest["files"]), 2)
                self.assertIsNotNone(safety)
                self.assertTrue(safety and safety.exists())
                local_data.verify_backup(safety)
                with closing(sqlite3.connect(database)) as connection:
                    value = connection.execute("select value from smoke").fetchone()[0]
                self.assertEqual(value, "before")


if __name__ == "__main__":
    unittest.main()
