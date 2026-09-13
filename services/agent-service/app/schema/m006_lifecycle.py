"""Governed knowledge schema and one-time backfill of approved v1 facts."""

import json
import sqlite3
import uuid

from app.schema.common import ensure_column


def migrate(conn: sqlite3.Connection) -> None:
    """Create lifecycle-owned tables and migrate already-approved knowledge to v1."""
    conn.execute(
        """
        create table if not exists knowledge_versions (
            knowledge_version_id text primary key,
            candidate_id text not null,
            tenant_id text not null,
            owner_id text not null,
            version_number integer not null,
            statement text not null,
            evidence_json text not null,
            document_id text not null unique,
            content_sha256 text not null,
            status text not null,
            predecessor_version_id text,
            successor_version_id text,
            approved_by text not null,
            approved_at text not null,
            invalidated_by text,
            invalidated_at text,
            invalidation_reason text,
            unique(candidate_id, version_number),
            foreign key (candidate_id) references knowledge_candidates(candidate_id)
        )
        """
    )
    conn.execute(
        """
        create index if not exists idx_knowledge_version_scope_status
        on knowledge_versions(tenant_id, owner_id, status, approved_at)
        """
    )
    conn.execute(
        """
        create table if not exists knowledge_lifecycle_requests (
            request_id text primary key,
            candidate_id text not null,
            tenant_id text not null,
            owner_id text not null,
            action text not null,
            reason text not null,
            replacement_statement text,
            replacement_evidence_json text not null default '[]',
            status text not null,
            pending_candidate_id text,
            requested_by text not null,
            requested_at text not null,
            decided_by text,
            decided_at text,
            resulting_version_id text,
            foreign key (candidate_id) references knowledge_candidates(candidate_id)
        )
        """
    )
    ensure_column(
        conn,
        table="knowledge_lifecycle_requests",
        column="pending_candidate_id",
        definition="text",
    )
    conn.execute(
        """
        update knowledge_lifecycle_requests
        set pending_candidate_id = candidate_id
        where status = 'PENDING' and pending_candidate_id is null
        """
    )
    conn.execute(
        """
        create unique index if not exists uk_knowledge_lifecycle_pending
        on knowledge_lifecycle_requests(pending_candidate_id)
        """
    )
    _backfill_initial_knowledge_versions(conn)


def _backfill_initial_knowledge_versions(conn: sqlite3.Connection) -> None:
    rows = conn.execute(
        """
        select candidate.* from knowledge_candidates candidate
        where candidate.status = 'APPROVED'
          and candidate.knowledge_document_id is not null
          and not exists (
              select 1 from knowledge_versions version
              where version.candidate_id = candidate.candidate_id
          )
        """
    ).fetchall()
    changed = False
    for candidate in rows:
        knowledge_version_id = str(uuid.uuid5(
            uuid.NAMESPACE_URL,
            f"enterprise-insight:knowledge:{candidate['candidate_id']}:v1",
        ))
        approved_by = candidate["decided_by"] or candidate["created_by"]
        approved_at = (
            candidate["knowledge_published_at"]
            or candidate["decided_at"]
            or candidate["created_at"]
        )
        conn.execute(
            """
            insert into knowledge_versions (
                knowledge_version_id, candidate_id, tenant_id, owner_id,
                version_number, statement, evidence_json, document_id,
                content_sha256, status, approved_by, approved_at
            ) values (?, ?, ?, ?, 1, ?, ?, ?, ?, 'ACTIVE', ?, ?)
            """,
            (
                knowledge_version_id, candidate["candidate_id"], candidate["tenant_id"],
                candidate["owner_id"], candidate["statement"], candidate["evidence_json"],
                candidate["knowledge_document_id"], candidate["knowledge_content_sha256"],
                approved_by, approved_at,
            ),
        )
        document = conn.execute(
            "select metadata_json from documents where id = ?",
            (candidate["knowledge_document_id"],),
        ).fetchone()
        if document is not None:
            try:
                metadata = json.loads(document["metadata_json"] or "{}")
            except (TypeError, json.JSONDecodeError):
                metadata = {}
            metadata.update({
                "knowledge_version_id": knowledge_version_id,
                "knowledge_version_number": 1,
                "predecessor_version_id": None,
            })
            conn.execute(
                """
                update documents set metadata_json = ?, lifecycle_status = 'ACTIVE'
                where id = ?
                """,
                (
                    json.dumps(metadata, ensure_ascii=False, sort_keys=True),
                    candidate["knowledge_document_id"],
                ),
            )
        conn.execute(
            """
            update knowledge_candidates
            set knowledge_status = 'ACTIVE', active_knowledge_version_id = ?,
                knowledge_version_number = 1
            where candidate_id = ?
            """,
            (knowledge_version_id, candidate["candidate_id"]),
        )
        changed = True
    if changed:
        conn.execute("update system_meta set value = value + 1")
