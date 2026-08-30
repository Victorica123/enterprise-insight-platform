"""Immutable PRD versions and the governed artifacts derived from publication."""
from __future__ import annotations

import hashlib
import json
import sqlite3
import uuid
from datetime import datetime

from app import database
from app.graph_store import index_document_graph, init_graph_store
from app.analysis_models import (
    ActionItemDraft,
    AnalysisSessionResponse,
    KnowledgeCandidate,
    PublicationDeliverables,
    PublishedPrdVersion,
)


def init_publication_artifact_store() -> None:
    with database.connect() as conn:
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
        database.ensure_column(conn, "knowledge_candidates", "knowledge_document_id", "text")
        database.ensure_column(conn, "knowledge_candidates", "knowledge_content_sha256", "text")
        database.ensure_column(conn, "knowledge_candidates", "knowledge_published_at", "text")
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
        database.ensure_column(conn, "action_item_drafts", "ticket_id", "text")
        conn.execute(
            """
            create index if not exists idx_action_item_scope_status
            on action_item_drafts(tenant_id, owner_id, status, created_at)
            """
        )


def build_publication_deliverables(
    session: AnalysisSessionResponse,
    *,
    published_by: str,
    published_at: datetime,
) -> PublicationDeliverables:
    if session.prd is None:
        raise ValueError("Published PRD is required.")
    prd_payload = session.prd.model_dump(mode="json")
    canonical = json.dumps(
        prd_payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"),
    )
    version_id = str(uuid.uuid4())
    version = PublishedPrdVersion(
        version_id=version_id,
        session_id=session.session_id,
        tenant_id=session.tenant_id,
        owner_id=session.owner_id,
        version_number=1,
        content_sha256=hashlib.sha256(canonical.encode("utf-8")).hexdigest(),
        prd=session.prd.model_copy(deep=True),
        published_by=published_by,
        published_at=published_at,
    )
    candidates: list[KnowledgeCandidate] = []
    actions: list[ActionItemDraft] = []
    for requirement in session.prd.requirements:
        candidates.append(KnowledgeCandidate(
            candidate_id=str(uuid.uuid4()),
            session_id=session.session_id,
            version_id=version_id,
            tenant_id=session.tenant_id,
            owner_id=session.owner_id,
            requirement_id=requirement.requirement_id,
            statement=f"{requirement.title}：{requirement.description}",
            evidence=requirement.evidence,
            created_by=session.owner_id,
            created_at=published_at,
        ))
        criteria = "；".join(requirement.acceptance_criteria)
        actions.append(ActionItemDraft(
            action_item_id=str(uuid.uuid4()),
            session_id=session.session_id,
            version_id=version_id,
            tenant_id=session.tenant_id,
            owner_id=session.owner_id,
            requirement_id=requirement.requirement_id,
            title=f"落实 {requirement.title}"[:120],
            description=(
                f"来源：已发布 PRD {session.prd.title}\n"
                f"需求：{requirement.description}\n验收：{criteria}"
            )[:3000],
            priority="high" if any(term in requirement.description for term in ("风险", "阻塞", "必须")) else "medium",
            evidence=requirement.evidence,
            created_at=published_at,
            updated_at=published_at,
        ))
    return PublicationDeliverables(
        version=version, knowledge_candidates=candidates, action_items=actions,
    )


def persist_publication_deliverables(
    conn: sqlite3.Connection,
    deliverables: PublicationDeliverables,
) -> None:
    version = deliverables.version
    conn.execute(
        """
        insert into published_prd_versions (
            version_id, session_id, tenant_id, owner_id, version_number,
            content_sha256, prd_json, published_by, published_at
        ) values (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            version.version_id, version.session_id, version.tenant_id, version.owner_id,
            version.version_number, version.content_sha256,
            json.dumps(version.prd.model_dump(mode="json"), ensure_ascii=False),
            version.published_by, version.published_at.isoformat(),
        ),
    )
    conn.executemany(
        """
        insert into knowledge_candidates (
            candidate_id, session_id, version_id, tenant_id, owner_id,
            requirement_id, statement, evidence_json, status, created_by, created_at
        ) values (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        [(
            item.candidate_id, item.session_id, item.version_id, item.tenant_id,
            item.owner_id, item.requirement_id, item.statement,
            json.dumps([value.model_dump(mode="json") for value in item.evidence], ensure_ascii=False),
            item.status, item.created_by, item.created_at.isoformat(),
        ) for item in deliverables.knowledge_candidates],
    )
    conn.executemany(
        """
        insert into action_item_drafts (
            action_item_id, session_id, version_id, tenant_id, owner_id,
            requirement_id, title, description, priority, evidence_json,
            status, pending_action_id, ticket_id, created_at, updated_at
        ) values (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        [(
            item.action_item_id, item.session_id, item.version_id, item.tenant_id,
            item.owner_id, item.requirement_id, item.title, item.description,
            item.priority,
            json.dumps([value.model_dump(mode="json") for value in item.evidence], ensure_ascii=False),
            item.status, item.pending_action_id, item.ticket_id,
            item.created_at.isoformat(), item.updated_at.isoformat(),
        ) for item in deliverables.action_items],
    )


def get_publication_deliverables(
    session_id: str,
    tenant_id: str,
) -> PublicationDeliverables | None:
    init_publication_artifact_store()
    with database.connect() as conn:
        version_row = conn.execute(
            """
            select * from published_prd_versions
            where session_id = ? and tenant_id = ? order by version_number desc limit 1
            """,
            (session_id, tenant_id),
        ).fetchone()
        if version_row is None:
            return None
        candidate_rows = conn.execute(
            "select * from knowledge_candidates where version_id = ? order by requirement_id",
            (version_row["version_id"],),
        ).fetchall()
        action_rows = conn.execute(
            "select * from action_item_drafts where version_id = ? order by requirement_id",
            (version_row["version_id"],),
        ).fetchall()
    return PublicationDeliverables(
        version=_version_from_row(version_row),
        knowledge_candidates=[_candidate_from_row(row) for row in candidate_rows],
        action_items=[_action_from_row(row) for row in action_rows],
    )


def decide_knowledge_candidate(
    candidate_id: str,
    *,
    tenant_id: str,
    actor_id: str,
    approved: bool,
    decided_at: datetime,
) -> KnowledgeCandidate | None:
    init_publication_artifact_store()
    init_graph_store()
    status = "APPROVED" if approved else "REJECTED"
    with database.connect() as conn:
        # Serialize the read-before-materialize decision. Without an immediate
        # write reservation, two approvers can both observe PENDING and race to
        # insert the same managed document before the final CAS update.
        conn.execute("begin immediate")
        candidate = conn.execute(
            """
            select * from knowledge_candidates
            where candidate_id = ? and tenant_id = ? and status = 'PENDING'
            """,
            (candidate_id, tenant_id),
        ).fetchone()
        if candidate is None:
            return None

        knowledge_document_id: str | None = None
        knowledge_content_sha256: str | None = None
        knowledge_published_at: str | None = None
        if approved:
            knowledge_document_id = f"knowledge-{candidate_id}"
            knowledge_content, knowledge_content_sha256, metadata = _build_approved_knowledge(candidate)
            knowledge_published_at = decided_at.isoformat()
            database.insert_document(
                document_id=knowledge_document_id,
                filename=f"approved-knowledge-{candidate_id[:8]}.md",
                chunks=[(f"已批准知识 / {candidate['requirement_id']}", knowledge_content)],
                conn=conn,
                tenant_id=candidate["tenant_id"],
                owner_id=candidate["owner_id"],
                source_type="knowledge",
                external_id=candidate_id,
                source_version=1,
                payload_sha256=knowledge_content_sha256,
                metadata=metadata,
            )
            index_document_graph(knowledge_document_id, conn=conn)

        cursor = conn.execute(
            """
            update knowledge_candidates
            set status = ?, decided_by = ?, decided_at = ?,
                knowledge_document_id = ?, knowledge_content_sha256 = ?, knowledge_published_at = ?
            where candidate_id = ? and tenant_id = ? and status = 'PENDING'
            """,
            (
                status, actor_id, decided_at.isoformat(), knowledge_document_id,
                knowledge_content_sha256, knowledge_published_at, candidate_id, tenant_id,
            ),
        )
        if cursor.rowcount != 1:
            return None
        row = conn.execute(
            "select * from knowledge_candidates where candidate_id = ? and tenant_id = ?",
            (candidate_id, tenant_id),
        ).fetchone()
    return _candidate_from_row(row) if row else None


def _build_approved_knowledge(candidate: sqlite3.Row) -> tuple[str, str, dict[str, object]]:
    evidence = json.loads(candidate["evidence_json"])
    evidence_lines: list[str] = []
    for item in evidence:
        excerpt = " ".join(str(item.get("excerpt", "")).split())
        location = item.get("filename", "")
        if item.get("source_type") == "video":
            location += f" [{item.get('start_ms', 0)}-{item.get('end_ms', 0)}ms]"
        evidence_lines.append(
            f"- {item.get('source_type', 'document')} · {location} · {excerpt}"
        )
    content = "\n".join([
        f"# 已批准业务知识：{candidate['requirement_id']}",
        "",
        candidate["statement"],
        "",
        "## 可验证证据",
        *evidence_lines,
        "",
        "## 治理来源",
        f"- PRD version: {candidate['version_id']}",
        f"- Analysis session: {candidate['session_id']}",
        f"- Knowledge candidate: {candidate['candidate_id']}",
    ])
    digest = hashlib.sha256(content.encode("utf-8")).hexdigest()
    metadata: dict[str, object] = {
        "managed_type": "approved_knowledge",
        "candidate_id": candidate["candidate_id"],
        "analysis_session_id": candidate["session_id"],
        "prd_version_id": candidate["version_id"],
        "requirement_id": candidate["requirement_id"],
        "evidence": evidence,
    }
    return content, digest, metadata


def get_action_item(action_item_id: str, tenant_id: str) -> ActionItemDraft | None:
    init_publication_artifact_store()
    with database.connect() as conn:
        row = conn.execute(
            "select * from action_item_drafts where action_item_id = ? and tenant_id = ?",
            (action_item_id, tenant_id),
        ).fetchone()
    return _action_from_row(row) if row else None


def mark_action_ticket_pending(
    action_item_id: str,
    *,
    tenant_id: str,
    pending_action_id: str,
    updated_at: datetime,
) -> ActionItemDraft | None:
    init_publication_artifact_store()
    with database.connect() as conn:
        cursor = conn.execute(
            """
            update action_item_drafts
            set status = 'TICKET_PENDING_APPROVAL', pending_action_id = ?, updated_at = ?
            where action_item_id = ? and tenant_id = ? and status = 'DRAFT'
            """,
            (pending_action_id, updated_at.isoformat(), action_item_id, tenant_id),
        )
        if cursor.rowcount != 1:
            return None
        row = conn.execute(
            "select * from action_item_drafts where action_item_id = ? and tenant_id = ?",
            (action_item_id, tenant_id),
        ).fetchone()
    return _action_from_row(row) if row else None


def settle_action_ticket(
    pending_action_id: str,
    *,
    tenant_id: str,
    action_status: str,
    ticket_id: str | None,
    updated_at: datetime,
) -> ActionItemDraft | None:
    """Project a terminal controlled-tool result back into its PRD action item."""
    init_publication_artifact_store()
    projected = {
        "succeeded": "TICKET_CREATED",
        "rejected": "TICKET_REJECTED",
        "failed": "TICKET_FAILED",
        "expired": "TICKET_FAILED",
    }.get(action_status)
    if projected is None:
        return None
    with database.connect() as conn:
        conn.execute(
            """
            update action_item_drafts
            set status = ?, ticket_id = coalesce(?, ticket_id), updated_at = ?
            where pending_action_id = ? and tenant_id = ?
              and status = 'TICKET_PENDING_APPROVAL'
            """,
            (projected, ticket_id, updated_at.isoformat(), pending_action_id, tenant_id),
        )
        row = conn.execute(
            "select * from action_item_drafts where pending_action_id = ? and tenant_id = ?",
            (pending_action_id, tenant_id),
        ).fetchone()
    return _action_from_row(row) if row else None


def _version_from_row(row: sqlite3.Row) -> PublishedPrdVersion:
    return PublishedPrdVersion.model_validate({
        **dict(row), "prd": json.loads(row["prd_json"]),
    })


def _candidate_from_row(row: sqlite3.Row) -> KnowledgeCandidate:
    return KnowledgeCandidate.model_validate({
        **dict(row), "evidence": json.loads(row["evidence_json"]),
    })


def _action_from_row(row: sqlite3.Row) -> ActionItemDraft:
    return ActionItemDraft.model_validate({
        **dict(row), "evidence": json.loads(row["evidence_json"]),
    })
