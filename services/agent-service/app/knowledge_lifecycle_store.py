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
    """Compatibility entry for older callers with a migration connection."""
    from app.schema.m006_lifecycle import migrate
    migrate(conn)





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
