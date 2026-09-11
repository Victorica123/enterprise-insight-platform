from __future__ import annotations

import hashlib
import json
import sqlite3
import uuid
from collections.abc import Callable
from datetime import datetime

from app import database
from app.analysis_models import GovernedKnowledgeVersion, KnowledgeLifecycleRequest
from app.evidence_provenance import validate_and_normalize_evidence

GraphIndexer = Callable[..., dict[str, int]]
GraphScopeRebuilder = Callable[..., None]


def init_knowledge_lifecycle_store(conn: sqlite3.Connection) -> None:
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
    database.ensure_column(
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
        database.bump_content_revision(conn)


def materialize_knowledge_version(
    conn: sqlite3.Connection,
    candidate: sqlite3.Row,
    *,
    statement: str,
    evidence: list[dict[str, object]],
    version_number: int,
    predecessor_version_id: str | None,
    actor_id: str,
    decided_at: datetime,
    index_document_graph: GraphIndexer,
) -> GovernedKnowledgeVersion:
    knowledge_version_id = str(uuid.uuid4())
    document_id = (
        f"knowledge-{candidate['candidate_id']}"
        if version_number == 1
        else f"knowledge-{candidate['candidate_id']}-v{version_number}"
    )
    content, digest, metadata = _build_approved_knowledge(
        candidate,
        statement=statement,
        evidence=evidence,
        knowledge_version_id=knowledge_version_id,
        version_number=version_number,
        predecessor_version_id=predecessor_version_id,
    )
    database.insert_document(
        document_id=document_id,
        filename=f"approved-knowledge-{candidate['candidate_id'][:8]}-v{version_number}.md",
        chunks=[(f"已批准知识 / {candidate['requirement_id']} / v{version_number}", content)],
        conn=conn,
        tenant_id=candidate["tenant_id"],
        owner_id=candidate["owner_id"],
        source_type="knowledge",
        external_id=candidate["candidate_id"],
        source_version=version_number,
        payload_sha256=digest,
        metadata=metadata,
    )
    conn.execute(
        """
        insert into knowledge_versions (
            knowledge_version_id, candidate_id, tenant_id, owner_id, version_number,
            statement, evidence_json, document_id, content_sha256, status,
            predecessor_version_id, approved_by, approved_at
        ) values (?, ?, ?, ?, ?, ?, ?, ?, ?, 'ACTIVE', ?, ?, ?)
        """,
        (
            knowledge_version_id, candidate["candidate_id"], candidate["tenant_id"],
            candidate["owner_id"], version_number, statement,
            json.dumps(evidence, ensure_ascii=False), document_id, digest,
            predecessor_version_id, actor_id, decided_at.isoformat(),
        ),
    )
    index_document_graph(document_id, conn=conn)
    return GovernedKnowledgeVersion(
        knowledge_version_id=knowledge_version_id,
        candidate_id=candidate["candidate_id"],
        tenant_id=candidate["tenant_id"],
        owner_id=candidate["owner_id"],
        version_number=version_number,
        statement=statement,
        evidence=evidence,
        document_id=document_id,
        content_sha256=digest,
        status="ACTIVE",
        predecessor_version_id=predecessor_version_id,
        approved_by=actor_id,
        approved_at=decided_at,
    )


def _build_approved_knowledge(
    candidate: sqlite3.Row,
    *,
    statement: str,
    evidence: list[dict[str, object]],
    knowledge_version_id: str,
    version_number: int,
    predecessor_version_id: str | None,
) -> tuple[str, str, dict[str, object]]:
    evidence_lines: list[str] = []
    for item in evidence:
        excerpt = " ".join(str(item.get("excerpt", "")).split())
        location = str(item.get("filename", ""))
        if item.get("source_type") == "video":
            location += f" [{item.get('start_ms', 0)}-{item.get('end_ms', 0)}ms]"
        evidence_lines.append(
            f"- {item.get('source_type', 'document')} · {location} · {excerpt}"
        )
    content = "\n".join([
        f"# 已批准业务知识：{candidate['requirement_id']}",
        "",
        statement,
        "",
        "## 可验证证据",
        *evidence_lines,
        "",
        "## 治理来源",
        f"- PRD version: {candidate['version_id']}",
        f"- Analysis session: {candidate['session_id']}",
        f"- Knowledge candidate: {candidate['candidate_id']}",
        f"- Knowledge version: {knowledge_version_id} (v{version_number})",
        f"- Predecessor: {predecessor_version_id or 'none'}",
    ])
    digest = hashlib.sha256(content.encode("utf-8")).hexdigest()
    metadata: dict[str, object] = {
        "managed_type": "approved_knowledge",
        "candidate_id": candidate["candidate_id"],
        "analysis_session_id": candidate["session_id"],
        "prd_version_id": candidate["version_id"],
        "requirement_id": candidate["requirement_id"],
        "evidence": evidence,
        "knowledge_version_id": knowledge_version_id,
        "knowledge_version_number": version_number,
        "predecessor_version_id": predecessor_version_id,
    }
    return content, digest, metadata


def request_knowledge_lifecycle(
    candidate_id: str,
    *,
    tenant_id: str,
    actor_id: str,
    action: str,
    reason: str,
    replacement_statement: str | None,
    replacement_evidence: list[dict[str, object]],
    requested_at: datetime,
    evidence_owner_id: str | None = None,
) -> KnowledgeLifecycleRequest | None:
    with database.connect() as conn:
        conn.execute("begin immediate")
        candidate = conn.execute(
            """
            select * from knowledge_candidates
            where candidate_id = ? and tenant_id = ? and status = 'APPROVED'
              and knowledge_status = 'ACTIVE' and pending_lifecycle_request_id is null
            """,
            (candidate_id, tenant_id),
        ).fetchone()
        if candidate is None:
            return None
        current = conn.execute(
            """
            select * from knowledge_versions
            where knowledge_version_id = ? and candidate_id = ? and status = 'ACTIVE'
            """,
            (candidate["active_knowledge_version_id"], candidate_id),
        ).fetchone()
        if current is None:
            return None
        normalized_statement = replacement_statement.strip() if replacement_statement else None
        if action == "SUPERSEDE" and (
            not normalized_statement
            or normalized_statement == current["statement"]
            or not replacement_evidence
        ):
            return None
        normalized_evidence = (
            validate_and_normalize_evidence(
                conn,
                replacement_evidence,
                tenant_id=tenant_id,
                owner_id=evidence_owner_id,
            )
            if action == "SUPERSEDE"
            else []
        )
        request_id = str(uuid.uuid4())
        conn.execute(
            """
            insert into knowledge_lifecycle_requests (
                request_id, candidate_id, tenant_id, owner_id, action, reason,
                replacement_statement, replacement_evidence_json, status,
                pending_candidate_id, requested_by, requested_at
            ) values (?, ?, ?, ?, ?, ?, ?, ?, 'PENDING', ?, ?, ?)
            """,
            (
                request_id, candidate_id, tenant_id, candidate["owner_id"], action,
                reason.strip(), normalized_statement,
                json.dumps(normalized_evidence, ensure_ascii=False), candidate_id, actor_id,
                requested_at.isoformat(),
            ),
        )
        cursor = conn.execute(
            """
            update knowledge_candidates set pending_lifecycle_request_id = ?
            where candidate_id = ? and tenant_id = ?
              and knowledge_status = 'ACTIVE' and pending_lifecycle_request_id is null
            """,
            (request_id, candidate_id, tenant_id),
        )
        if cursor.rowcount != 1:
            return None
        row = conn.execute(
            "select * from knowledge_lifecycle_requests where request_id = ?",
            (request_id,),
        ).fetchone()
    return lifecycle_request_from_row(row) if row else None


def decide_knowledge_lifecycle(
    request_id: str,
    *,
    candidate_id: str,
    tenant_id: str,
    actor_id: str,
    approved: bool,
    decided_at: datetime,
    index_document_graph: GraphIndexer,
    rebuild_graph_scope: GraphScopeRebuilder,
    evidence_owner_id: str | None = None,
) -> KnowledgeLifecycleRequest | None:
    with database.connect() as conn:
        conn.execute("begin immediate")
        lifecycle = conn.execute(
            """
            select * from knowledge_lifecycle_requests
            where request_id = ? and candidate_id = ? and tenant_id = ? and status = 'PENDING'
            """,
            (request_id, candidate_id, tenant_id),
        ).fetchone()
        candidate = conn.execute(
            """
            select * from knowledge_candidates
            where candidate_id = ? and tenant_id = ? and status = 'APPROVED'
              and pending_lifecycle_request_id = ?
            """,
            (candidate_id, tenant_id, request_id),
        ).fetchone()
        if lifecycle is None or candidate is None:
            return None

        resulting_version_id: str | None = None
        if approved:
            current = conn.execute(
                """
                select * from knowledge_versions
                where knowledge_version_id = ? and candidate_id = ? and status = 'ACTIVE'
                """,
                (candidate["active_knowledge_version_id"], candidate_id),
            ).fetchone()
            if current is None:
                return None
            if lifecycle["action"] == "REVOKE":
                resulting_version_id = current["knowledge_version_id"]
                conn.execute(
                    """
                    update knowledge_versions
                    set status = 'REVOKED', invalidated_by = ?, invalidated_at = ?,
                        invalidation_reason = ?
                    where knowledge_version_id = ? and status = 'ACTIVE'
                    """,
                    (actor_id, decided_at.isoformat(), lifecycle["reason"], resulting_version_id),
                )
                conn.execute(
                    """
                    update documents
                    set lifecycle_status = 'REVOKED', lifecycle_changed_by = ?,
                        lifecycle_changed_at = ?, lifecycle_reason = ?
                    where id = ? and lifecycle_status = 'ACTIVE'
                    """,
                    (actor_id, decided_at.isoformat(), lifecycle["reason"], current["document_id"]),
                )
                conn.execute(
                    """
                    update knowledge_candidates
                    set knowledge_status = 'REVOKED', active_knowledge_version_id = null,
                        pending_lifecycle_request_id = null
                    where candidate_id = ? and pending_lifecycle_request_id = ?
                    """,
                    (candidate_id, request_id),
                )
            else:
                replacement_evidence = validate_and_normalize_evidence(
                    conn,
                    json.loads(lifecycle["replacement_evidence_json"]),
                    tenant_id=tenant_id,
                    owner_id=evidence_owner_id,
                )
                successor = materialize_knowledge_version(
                    conn,
                    candidate,
                    statement=lifecycle["replacement_statement"],
                    evidence=replacement_evidence,
                    version_number=int(current["version_number"]) + 1,
                    predecessor_version_id=current["knowledge_version_id"],
                    actor_id=actor_id,
                    decided_at=decided_at,
                    index_document_graph=index_document_graph,
                )
                resulting_version_id = successor.knowledge_version_id
                conn.execute(
                    """
                    update knowledge_versions
                    set status = 'SUPERSEDED', successor_version_id = ?,
                        invalidated_by = ?, invalidated_at = ?, invalidation_reason = ?
                    where knowledge_version_id = ? and status = 'ACTIVE'
                    """,
                    (
                        successor.knowledge_version_id, actor_id, decided_at.isoformat(),
                        lifecycle["reason"], current["knowledge_version_id"],
                    ),
                )
                conn.execute(
                    """
                    update documents
                    set lifecycle_status = 'SUPERSEDED', superseded_by_document_id = ?,
                        lifecycle_changed_by = ?, lifecycle_changed_at = ?, lifecycle_reason = ?
                    where id = ? and lifecycle_status = 'ACTIVE'
                    """,
                    (
                        successor.document_id, actor_id, decided_at.isoformat(),
                        lifecycle["reason"], current["document_id"],
                    ),
                )
                conn.execute(
                    "update documents set supersedes_document_id = ? where id = ?",
                    (current["document_id"], successor.document_id),
                )
                conn.execute(
                    """
                    update knowledge_candidates
                    set knowledge_document_id = ?, knowledge_content_sha256 = ?,
                        knowledge_published_at = ?, knowledge_status = 'ACTIVE',
                        active_knowledge_version_id = ?, knowledge_version_number = ?,
                        pending_lifecycle_request_id = null
                    where candidate_id = ? and pending_lifecycle_request_id = ?
                    """,
                    (
                        successor.document_id, successor.content_sha256,
                        successor.approved_at.isoformat(), successor.knowledge_version_id,
                        successor.version_number, candidate_id, request_id,
                    ),
                )
            database.bump_content_revision(conn, str(candidate["tenant_id"]))
            rebuild_graph_scope(
                conn=conn, tenant_id=candidate["tenant_id"], owner_id=candidate["owner_id"],
            )
        else:
            conn.execute(
                """
                update knowledge_candidates set pending_lifecycle_request_id = null
                where candidate_id = ? and pending_lifecycle_request_id = ?
                """,
                (candidate_id, request_id),
            )

        cursor = conn.execute(
            """
            update knowledge_lifecycle_requests
            set status = ?, pending_candidate_id = null, decided_by = ?,
                decided_at = ?, resulting_version_id = ?
            where request_id = ? and candidate_id = ? and tenant_id = ? and status = 'PENDING'
            """,
            (
                "APPROVED" if approved else "REJECTED", actor_id,
                decided_at.isoformat(), resulting_version_id, request_id,
                candidate_id, tenant_id,
            ),
        )
        if cursor.rowcount != 1:
            return None
        row = conn.execute(
            "select * from knowledge_lifecycle_requests where request_id = ?",
            (request_id,),
        ).fetchone()
    return lifecycle_request_from_row(row) if row else None


def knowledge_version_from_row(row: sqlite3.Row) -> GovernedKnowledgeVersion:
    return GovernedKnowledgeVersion(
        **dict(row), evidence=json.loads(row["evidence_json"]),
    )


def lifecycle_request_from_row(row: sqlite3.Row) -> KnowledgeLifecycleRequest:
    return KnowledgeLifecycleRequest(
        **dict(row), replacement_evidence=json.loads(row["replacement_evidence_json"]),
    )
