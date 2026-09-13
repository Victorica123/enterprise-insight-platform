"""Upgrade legacy global graph identities into the legacy tenant scope."""

import sqlite3


def migrate(conn: sqlite3.Connection) -> None:
    """Migrate the V4 global graph to tenant/owner composite identities once."""
    entity_exists = conn.execute(
        "select 1 from sqlite_master where type = 'table' and name = 'graph_entities'"
    ).fetchone()
    if entity_exists and not _has_column(conn, "graph_entities", "tenant_id"):
        conn.execute("alter table graph_entities rename to graph_entities_legacy")
        conn.execute("alter table graph_relations rename to graph_relations_legacy")
        conn.execute("alter table graph_meta rename to graph_meta_legacy")

    conn.execute(
        """
        create table if not exists graph_entities (
            entity_id varchar(128) primary key,
            tenant_id varchar(128) not null default 'legacy',
            owner_id varchar(128) not null default 'legacy',
            name varchar(128) not null,
            entity_type varchar(64) not null,
            mention_count integer not null default 1,
            document_ids text not null default '[]',
            created_at text not null,
            unique(tenant_id, owner_id, name, entity_type)
        )
        """
    )
    conn.execute(
        """
        create table if not exists graph_relations (
            relation_id varchar(128) primary key,
            tenant_id varchar(128) not null default 'legacy',
            owner_id varchar(128) not null default 'legacy',
            source_name varchar(128) not null,
            source_type varchar(64) not null,
            relation_type varchar(64) not null,
            target_name varchar(128) not null,
            target_type varchar(64) not null,
            evidence text not null default '',
            document_id varchar(128) not null default '',
            filename varchar(191) not null default '',
            chunk_index integer not null default 0,
            created_at text not null,
            unique(tenant_id, owner_id, source_name, relation_type, target_name, document_id, chunk_index)
        )
        """
    )
    conn.execute(
        """
        create table if not exists graph_meta (
            tenant_id varchar(128) not null default 'legacy',
            owner_id varchar(128) not null default 'legacy',
            key varchar(128) not null,
            value text not null default '',
            primary key (tenant_id, owner_id, key)
        )
        """
    )
    legacy_exists = conn.execute(
        "select 1 from sqlite_master where type = 'table' and name = 'graph_entities_legacy'"
    ).fetchone()
    if legacy_exists:
        conn.execute(
            """
            insert or ignore into graph_entities (
                entity_id, tenant_id, owner_id, name, entity_type,
                mention_count, document_ids, created_at
            )
            select entity_id, 'legacy', 'legacy', name, entity_type,
                   mention_count, document_ids, created_at
            from graph_entities_legacy
            """
        )
        conn.execute(
            """
            insert or ignore into graph_relations (
                relation_id, tenant_id, owner_id, source_name, source_type, relation_type,
                target_name, target_type, evidence, document_id, filename, chunk_index, created_at
            )
            select relation_id, 'legacy', 'legacy', source_name, source_type, relation_type,
                   target_name, target_type, evidence, document_id, filename, chunk_index, created_at
            from graph_relations_legacy
            """
        )
        conn.execute(
            """
            insert or ignore into graph_meta (tenant_id, owner_id, key, value)
            select 'legacy', 'legacy', key, value from graph_meta_legacy
            """
        )
        conn.execute("drop table graph_entities_legacy")
        conn.execute("drop table graph_relations_legacy")
        conn.execute("drop table graph_meta_legacy")

    conn.execute(
        "create index if not exists idx_graph_entities_scope on graph_entities(tenant_id, owner_id, entity_type)"
    )
    conn.execute(
        "create index if not exists idx_graph_relations_source on graph_relations(tenant_id, owner_id, source_name)"
    )
    conn.execute(
        "create index if not exists idx_graph_relations_target on graph_relations(tenant_id, owner_id, target_name)"
    )


def _has_column(conn: sqlite3.Connection, table: str, column: str) -> bool:
    return any(row["name"] == column for row in conn.execute(f"pragma table_info({table})"))
