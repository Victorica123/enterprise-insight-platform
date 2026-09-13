"""Baseline migration copied from the established domain store; append new versions."""

from app.schema.common import ensure_column


def migrate(conn) -> None:
    conn.execute(
        """
        create table if not exists analysis_sessions (
            session_id text primary key,
            tenant_id text not null,
            owner_id text not null,
            objective text not null,
            asset_ids_json text not null,
            status text not null,
            current_stage integer not null,
            checkpoint_version integer not null default 1,
            evidence_revision integer not null default 0,
            evidence_snapshot_sha256 text not null default '',
            evidence_snapshot_json text not null default '[]',
            retrieval_mode text not null default 'hybrid',
            resume_token text,
            stages_json text not null,
            open_questions_json text not null,
            confirmations_json text not null,
            prd_json text,
            publication_json text,
            created_at text not null,
            updated_at text not null
        )
        """
    )
    conn.execute(
        """
        create index if not exists idx_analysis_tenant_owner_created
        on analysis_sessions(tenant_id, owner_id, created_at desc)
        """
    )
    ensure_column(
        conn, table="analysis_sessions", column="publication_json", definition="text"
    )
    ensure_column(
        conn, table="analysis_sessions", column="checkpoint_version",
        definition="integer not null default 1",
    )
    ensure_column(
        conn, table="analysis_sessions", column="evidence_revision",
        definition="integer not null default 0",
    )
    ensure_column(
        conn, table="analysis_sessions", column="evidence_snapshot_sha256",
        definition="text not null default ''",
    )
    ensure_column(
        conn, table="analysis_sessions", column="evidence_snapshot_json",
        definition="text not null default '[]'",
    )
    ensure_column(
        conn, table="analysis_sessions", column="retrieval_mode",
        definition="text not null default 'hybrid'",
    )
    conn.execute(
        """
        create table if not exists analysis_audit_events (
            event_id text primary key,
            session_id text not null,
            tenant_id text not null,
            action text not null,
            actor_id text not null,
            actor_role text not null,
            details_json text not null,
            created_at text not null,
            foreign key (session_id) references analysis_sessions(session_id)
        )
        """
    )
    conn.execute(
        """
        create index if not exists idx_analysis_audit_session_created
        on analysis_audit_events(tenant_id, session_id, created_at)
        """
    )
