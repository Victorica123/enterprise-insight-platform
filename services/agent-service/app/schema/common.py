"""Compatibility helpers shared by numbered schema migrations."""

import sqlite3


def ensure_column(conn: sqlite3.Connection, table: str, column: str, definition: str) -> None:
    columns = conn.execute(f"pragma table_info({table})").fetchall()
    if any(row["name"] == column for row in columns):
        return

    try:
        conn.execute(f"alter table {table} add column {column} {definition}")
    except sqlite3.OperationalError:
        # Two request threads/processes may both observe an old schema before
        # SQLite serializes ALTER TABLE. If the winner committed the same
        # column while this statement waited, the migration is already done.
        refreshed = conn.execute(f"pragma table_info({table})").fetchall()
        if any(row["name"] == column for row in refreshed):
            return
        raise
