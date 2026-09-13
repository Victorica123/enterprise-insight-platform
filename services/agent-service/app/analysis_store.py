from __future__ import annotations

import json
from datetime import UTC, datetime
from typing import Any

from app import database
from app.analysis_evidence import (
    AnalysisEvidenceSnapshot,
    empty_snapshot_sha256,
    restore_analysis_evidence_snapshot,
)
from app.analysis_models import AnalysisAuditEvent, AnalysisSessionResponse, PublicationDeliverables
from app.publication_artifacts import (
    init_publication_artifact_store,
    persist_publication_deliverables,
)


def init_analysis_store() -> None:
    database.init_db()


def save_session(
    session: AnalysisSessionResponse,
    evidence_snapshot: AnalysisEvidenceSnapshot,
) -> None:
    init_analysis_store()
    payload = session.model_dump(mode="json")
    with database.connect() as conn:
        conn.execute(
            """
            insert into analysis_sessions (
                session_id, tenant_id, owner_id, objective, asset_ids_json, status,
                current_stage, checkpoint_version, evidence_revision,
                evidence_snapshot_sha256, evidence_snapshot_json, retrieval_mode,
                resume_token, stages_json, open_questions_json,
                confirmations_json, prd_json, publication_json, created_at, updated_at
            ) values (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            on conflict(session_id) do update set
                status=excluded.status,
                current_stage=excluded.current_stage,
                checkpoint_version=excluded.checkpoint_version,
                resume_token=excluded.resume_token,
                stages_json=excluded.stages_json,
                open_questions_json=excluded.open_questions_json,
                confirmations_json=excluded.confirmations_json,
                prd_json=excluded.prd_json,
                publication_json=excluded.publication_json,
                updated_at=excluded.updated_at
            """,
            (
                session.session_id, session.tenant_id, session.owner_id, session.objective,
                json.dumps(session.asset_ids, ensure_ascii=False), session.status,
                session.current_stage, session.checkpoint_version,
                session.evidence_revision, session.evidence_snapshot_sha256,
                evidence_snapshot.payload_json,
                session.retrieval_mode, session.resume_token,
                json.dumps(payload["stages"], ensure_ascii=False),
                json.dumps(payload["open_questions"], ensure_ascii=False),
                json.dumps(session.confirmations, ensure_ascii=False),
                json.dumps(payload["prd"], ensure_ascii=False) if payload["prd"] else None,
                json.dumps(payload["publication"], ensure_ascii=False) if payload["publication"] else None,
                session.created_at.isoformat(), session.updated_at.isoformat(),
            ),
        )


def get_session(session_id: str, tenant_id: str, owner_id: str) -> AnalysisSessionResponse | None:
    init_analysis_store()
    with database.connect() as conn:
        row = conn.execute(
            """
            select * from analysis_sessions
            where session_id = ? and tenant_id = ? and owner_id = ?
            """,
            (session_id, tenant_id, owner_id),
        ).fetchone()
    return _from_row(row) if row else None


def list_sessions(
    tenant_id: str, owner_id: str | None, limit: int = 50,
) -> list[AnalysisSessionResponse]:
    init_analysis_store()
    owner_clause = " and owner_id = ?" if owner_id is not None else ""
    params: list[object] = [tenant_id]
    if owner_id is not None:
        params.append(owner_id)
    params.append(max(1, min(limit, 100)))
    with database.connect() as conn:
        rows = conn.execute(
            f"""
            select * from analysis_sessions
            where tenant_id = ?{owner_clause}
            order by created_at desc limit ?
            """,
            params,
        ).fetchall()
    return [_from_row(row) for row in rows]


def get_session_for_tenant(session_id: str, tenant_id: str) -> AnalysisSessionResponse | None:
    init_analysis_store()
    with database.connect() as conn:
        row = conn.execute(
            "select * from analysis_sessions where session_id = ? and tenant_id = ?",
            (session_id, tenant_id),
        ).fetchone()
    return _from_row(row) if row else None


def get_evidence_snapshot(session_id: str, tenant_id: str) -> AnalysisEvidenceSnapshot:
    init_analysis_store()
    with database.connect() as conn:
        row = conn.execute(
            """
            select evidence_revision, evidence_snapshot_sha256,
                   evidence_snapshot_json, retrieval_mode
            from analysis_sessions where session_id = ? and tenant_id = ?
            """,
            (session_id, tenant_id),
        ).fetchone()
    if row is None:
        raise LookupError("Analysis session not found.")
    return restore_analysis_evidence_snapshot(
        row["evidence_snapshot_json"],
        revision=int(row["evidence_revision"]),
        expected_sha256=row["evidence_snapshot_sha256"],
        retrieval_mode=row["retrieval_mode"],
    )


def transition_confirmation(
    session: AnalysisSessionResponse,
    *,
    expected_resume_token: str,
) -> bool:
    """Atomically consume one resume token and persist the next business checkpoint."""

    init_analysis_store()
    payload = session.model_dump(mode="json")
    with database.connect() as conn:
        cursor = conn.execute(
            """
            update analysis_sessions set
                status = ?, current_stage = ?, checkpoint_version = ?, resume_token = ?,
                stages_json = ?, open_questions_json = ?, confirmations_json = ?,
                prd_json = ?, publication_json = ?, updated_at = ?
            where session_id = ? and tenant_id = ? and owner_id = ?
              and status = 'WAITING_CONFIRMATION' and resume_token = ?
            """,
            (
                session.status, session.current_stage, session.checkpoint_version,
                session.resume_token, json.dumps(payload["stages"], ensure_ascii=False),
                json.dumps(payload["open_questions"], ensure_ascii=False),
                json.dumps(session.confirmations, ensure_ascii=False),
                json.dumps(payload["prd"], ensure_ascii=False) if payload["prd"] else None,
                json.dumps(payload["publication"], ensure_ascii=False) if payload["publication"] else None,
                session.updated_at.isoformat(), session.session_id, session.tenant_id,
                session.owner_id, expected_resume_token,
            ),
        )
        return cursor.rowcount == 1


def list_pending_publications(
    tenant_id: str, exclude_user_id: str, limit: int = 50,
) -> list[AnalysisSessionResponse]:
    init_analysis_store()
    with database.connect() as conn:
        rows = conn.execute(
            """
            select * from analysis_sessions
            where tenant_id = ? and owner_id != ? and status = 'PUBLISH_PENDING'
            order by updated_at asc limit ?
            """,
            (tenant_id, exclude_user_id, max(1, min(limit, 100))),
        ).fetchall()
    return [session for row in rows if (session := _from_row(row)).publication
            and session.publication.policy == "FOUR_EYES"]


def transition_session(
    session: AnalysisSessionResponse,
    *,
    expected_status: str,
    audit_event: AnalysisAuditEvent,
    publication_deliverables: PublicationDeliverables | None = None,
) -> bool:
    """Compare-and-set a publication transition and append its audit event atomically."""
    init_analysis_store()
    if publication_deliverables is not None:
        init_publication_artifact_store()
    payload = session.model_dump(mode="json")
    with database.connect() as conn:
        cursor = conn.execute(
            """
            update analysis_sessions set
                status = ?, current_stage = ?, resume_token = ?, stages_json = ?,
                open_questions_json = ?, confirmations_json = ?, prd_json = ?,
                publication_json = ?, updated_at = ?
            where session_id = ? and tenant_id = ? and status = ?
            """,
            (
                session.status, session.current_stage, session.resume_token,
                json.dumps(payload["stages"], ensure_ascii=False),
                json.dumps(payload["open_questions"], ensure_ascii=False),
                json.dumps(session.confirmations, ensure_ascii=False),
                json.dumps(payload["prd"], ensure_ascii=False) if payload["prd"] else None,
                json.dumps(payload["publication"], ensure_ascii=False) if payload["publication"] else None,
                session.updated_at.isoformat(), session.session_id, session.tenant_id, expected_status,
            ),
        )
        if cursor.rowcount != 1:
            return False
        event = audit_event.model_dump(mode="json")
        conn.execute(
            """
            insert into analysis_audit_events (
                event_id, session_id, tenant_id, action, actor_id,
                actor_role, details_json, created_at
            ) values (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                audit_event.event_id, audit_event.session_id, session.tenant_id,
                audit_event.action, audit_event.actor_id, audit_event.actor_role,
                json.dumps(event["details"], ensure_ascii=False), event["created_at"],
            ),
        )
        if publication_deliverables is not None:
            persist_publication_deliverables(conn, publication_deliverables)
    return True


def list_audit_events(
    session_id: str, tenant_id: str,
) -> list[AnalysisAuditEvent]:
    init_analysis_store()
    with database.connect() as conn:
        rows = conn.execute(
            """
            select event_id, session_id, action, actor_id, actor_role, details_json, created_at
            from analysis_audit_events
            where session_id = ? and tenant_id = ?
            order by created_at asc, event_id asc
            """,
            (session_id, tenant_id),
        ).fetchall()
    return [AnalysisAuditEvent.model_validate({
        "event_id": row["event_id"],
        "session_id": row["session_id"],
        "action": row["action"],
        "actor_id": row["actor_id"],
        "actor_role": row["actor_role"],
        "details": json.loads(row["details_json"]),
        "created_at": row["created_at"],
    }) for row in rows]


def utc_now() -> datetime:
    return datetime.now(UTC)


def _from_row(row: Any) -> AnalysisSessionResponse:
    return AnalysisSessionResponse.model_validate({
        "session_id": row["session_id"],
        "tenant_id": row["tenant_id"],
        "owner_id": row["owner_id"],
        "objective": row["objective"],
        "asset_ids": json.loads(row["asset_ids_json"]),
        "status": row["status"],
        "current_stage": row["current_stage"],
        "checkpoint_version": (
            int(row["checkpoint_version"]) if "checkpoint_version" in row.keys() else 1
        ),
        "evidence_revision": (
            int(row["evidence_revision"]) if "evidence_revision" in row.keys() else 0
        ),
        "evidence_snapshot_sha256": (
            row["evidence_snapshot_sha256"]
            if "evidence_snapshot_sha256" in row.keys() and row["evidence_snapshot_sha256"]
            else empty_snapshot_sha256()
        ),
        "retrieval_mode": (
            row["retrieval_mode"] if "retrieval_mode" in row.keys() else "hybrid"
        ),
        "resume_token": row["resume_token"],
        "stages": json.loads(row["stages_json"]),
        "open_questions": json.loads(row["open_questions_json"]),
        "confirmations": json.loads(row["confirmations_json"]),
        "prd": json.loads(row["prd_json"]) if row["prd_json"] else None,
        "publication": json.loads(row["publication_json"]) if row["publication_json"] else None,
        "created_at": row["created_at"],
        "updated_at": row["updated_at"],
    })
