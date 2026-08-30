from __future__ import annotations

import sqlite3
import unittest

from app import database


class _Rows:
    def __init__(self, rows: list[dict[str, str]]):
        self._rows = rows

    def fetchall(self) -> list[dict[str, str]]:
        return self._rows


class _ConcurrentMigrationConnection:
    def __init__(self) -> None:
        self.schema_reads = 0

    def execute(self, sql: str) -> _Rows:
        if sql.startswith("pragma table_info"):
            self.schema_reads += 1
            if self.schema_reads == 1:
                return _Rows([])
            return _Rows([{"name": "owner_id"}])
        if sql.startswith("alter table"):
            raise sqlite3.OperationalError("duplicate column name: owner_id")
        raise AssertionError(f"unexpected SQL: {sql}")


class EnsureColumnConcurrencyTests(unittest.TestCase):
    def test_accepts_duplicate_when_concurrent_migration_already_added_column(self) -> None:
        connection = _ConcurrentMigrationConnection()

        database.ensure_column(  # type: ignore[arg-type]
            connection,
            table="pending_actions",
            column="owner_id",
            definition="text not null default 'legacy'",
        )

        self.assertEqual(connection.schema_reads, 2)


if __name__ == "__main__":
    unittest.main()
