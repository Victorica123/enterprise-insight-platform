"""Baseline migration copied from the established domain store; append new versions."""

from app.schema.common import ensure_column


def migrate(conn) -> None:
    conn.execute(
        """
        create table if not exists published_prd_versions (
            version_id text primary key,
            session_id text not null,
            tenant_id text not null,
            owner_id text not null,
            version_number integer not null,
            content_sha256 text not null,
            prd_json text not null,
            published_by text not null,
            published_at text not null,
            unique(session_id, version_number),
            unique(session_id, content_sha256),
            foreign key (session_id) references analysis_sessions(session_id)
        )
        """
    )
    conn.execute(
        """
        create index if not exists idx_published_prd_scope
        on published_prd_versions(tenant_id, owner_id, published_at desc)
        """
    )
    conn.execute(
        """
        create table if not exists knowledge_candidates (
            candidate_id text primary key,
            session_id text not null,
            version_id text not null,
            tenant_id text not null,
            owner_id text not null,
            requirement_id text not null,
            statement text not null,
            evidence_json text not null,
            status text not null,
            created_by text not null,
            created_at text not null,
            decided_by text,
            decided_at text,
            unique(version_id, requirement_id),
            foreign key (version_id) references published_prd_versions(version_id)
        )
        """
    )
    ensure_column(conn, "knowledge_candidates", "knowledge_document_id", "text")
    ensure_column(conn, "knowledge_candidates", "knowledge_content_sha256", "text")
    ensure_column(conn, "knowledge_candidates", "knowledge_published_at", "text")
    ensure_column(conn, "knowledge_candidates", "knowledge_status", "text not null default 'NONE'")
    ensure_column(conn, "knowledge_candidates", "active_knowledge_version_id", "text")
    ensure_column(conn, "knowledge_candidates", "knowledge_version_number", "integer not null default 0")
    ensure_column(conn, "knowledge_candidates", "pending_lifecycle_request_id", "text")
    conn.execute(
        """
        create index if not exists idx_knowledge_candidate_scope_status
        on knowledge_candidates(tenant_id, owner_id, status, created_at)
        """
    )
    conn.execute(
        """
        create table if not exists action_item_drafts (
            action_item_id text primary key,
            session_id text not null,
            version_id text not null,
            tenant_id text not null,
            owner_id text not null,
            requirement_id text not null,
            title text not null,
            description text not null,
            priority text not null,
            evidence_json text not null,
            status text not null,
            pending_action_id text,
            ticket_id text,
            created_at text not null,
            updated_at text not null,
            unique(version_id, requirement_id),
            foreign key (version_id) references published_prd_versions(version_id)
        )
        """
    )
    ensure_column(conn, "action_item_drafts", "ticket_id", "text")
    conn.execute(
        """
        create index if not exists idx_action_item_scope_status
        on action_item_drafts(tenant_id, owner_id, status, created_at)
        """
    )
