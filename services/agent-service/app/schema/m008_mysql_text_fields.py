"""Widen non-indexed evidence and governance fields on existing MySQL databases.

SQLite TEXT already supports these payloads. Each MySQL ALTER is independently
retryable because DDL commits before the migration ledger can be written.
"""

from app.db_compat import MySqlConnectionCompat

_FIELDS = (
    ("analysis_sessions", "asset_ids_json", "longtext not null"),
    ("tickets", "source_document_ids", "longtext not null default ('[]')"),
    ("knowledge_lifecycle_requests", "reason", "longtext not null"),
    ("knowledge_lifecycle_requests", "replacement_statement", "longtext null"),
    ("knowledge_lifecycle_requests", "replacement_evidence_json", "longtext not null default ('[]')"),
    ("knowledge_versions", "invalidation_reason", "longtext null"),
    ("documents", "lifecycle_reason", "longtext null"),
)


def migrate(conn) -> None:
    if not isinstance(conn, MySqlConnectionCompat):
        return
    for table, column, definition in _FIELDS:
        row = conn.execute(
            "select data_type from information_schema.columns "
            "where table_schema = database() and table_name = ? and column_name = ?",
            (table, column),
        ).fetchone()
        if row is None:
            raise RuntimeError(f"Required migration column is missing: {table}.{column}")
        if row[0].lower() != "longtext":
            # Identifiers and definitions come exclusively from the frozen list above.
            conn.execute(f"alter table {table} modify column {column} {definition}")
