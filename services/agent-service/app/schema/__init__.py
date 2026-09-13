"""Ordered, idempotent migrations with a durable ledger and startup locking.

SQLite uses a write transaction. MySQL DDL auto-commits, so an advisory lock
serializes workers and each migration must remain safe to retry after failure.
Append versions rather than editing an applied migration.
"""

from hashlib import sha256

from app.schema import (
    m001_knowledge,
    m002_tickets,
    m003_graph,
    m004_analysis,
    m005_publication,
    m006_lifecycle,
    m007_conversations,
    m008_mysql_text_fields,
)

MIGRATIONS = (
    (1, "knowledge_and_observability", m001_knowledge.migrate),
    (2, "tickets_and_tool_audit", m002_tickets.migrate),
    (3, "scoped_graph", m003_graph.migrate),
    (4, "analysis_checkpoints", m004_analysis.migrate),
    (5, "publication_artifacts", m005_publication.migrate),
    (6, "governed_knowledge", m006_lifecycle.migrate),
    (7, "conversations", m007_conversations.migrate),
    (8, "mysql_evidence_and_governance_text", m008_mysql_text_fields.migrate),
)


def apply_migrations(conn, *, mysql: bool = False, identity: str = "sqlite") -> None:
    lock_name = "eip-schema-" + sha256(identity.encode()).hexdigest()[:40]
    if mysql:
        if conn.execute("select get_lock(?, 30)", (lock_name,)).fetchone()[0] != 1:
            raise RuntimeError("Could not acquire Agent schema migration lock.")
    else:
        conn.execute("begin immediate")
    try:
        conn.execute("""
            create table if not exists schema_migrations (
                version integer primary key,
                name text not null,
                applied_at text not null default current_timestamp
            )
        """)
        applied = {row["version"]: row["name"] for row in conn.execute("select version, name from schema_migrations")}
        known = {version: name for version, name, _ in MIGRATIONS}
        if any(known.get(version) != name for version, name in applied.items()):
            raise RuntimeError("Database schema is newer or differs from this application; use a compatible release.")
        for version, name, migrate in MIGRATIONS:
            if version not in applied:
                migrate(conn)
                conn.execute("insert into schema_migrations(version, name) values (?, ?)", (version, name))
                if mysql:
                    conn.commit()
    except BaseException:
        conn.rollback()
        raise
    finally:
        if mysql:
            conn.execute("select release_lock(?)", (lock_name,))
