from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any

from app import database
from app.analysis_models import AnalysisSessionResponse


def init_analysis_store() -> None:
    with database.connect() as conn:
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
                resume_token text,
                stages_json text not null,
                open_questions_json text not null,
                confirmations_json text not null,
                prd_json text,
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


def save_session(session: AnalysisSessionResponse) -> None:
    init_analysis_store()
    payload = session.model_dump(mode="json")
    with database.connect() as conn:
        conn.execute(
            """
            insert into analysis_sessions (
                session_id, tenant_id, owner_id, objective, asset_ids_json, status,
                current_stage, resume_token, stages_json, open_questions_json,
                confirmations_json, prd_json, created_at, updated_at
            ) values (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            on conflict(session_id) do update set
                status=excluded.status,
                current_stage=excluded.current_stage,
                resume_token=excluded.resume_token,
                stages_json=excluded.stages_json,
                open_questions_json=excluded.open_questions_json,
                confirmations_json=excluded.confirmations_json,
                prd_json=excluded.prd_json,
                updated_at=excluded.updated_at
            """,
            (
                session.session_id, session.tenant_id, session.owner_id, session.objective,
                json.dumps(session.asset_ids, ensure_ascii=False), session.status,
                session.current_stage, session.resume_token,
                json.dumps(payload["stages"], ensure_ascii=False),
                json.dumps(payload["open_questions"], ensure_ascii=False),
                json.dumps(session.confirmations, ensure_ascii=False),
                json.dumps(payload["prd"], ensure_ascii=False) if payload["prd"] else None,
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


def list_sessions(tenant_id: str, owner_id: str, limit: int = 50) -> list[AnalysisSessionResponse]:
    init_analysis_store()
    with database.connect() as conn:
        rows = conn.execute(
            """
            select * from analysis_sessions
            where tenant_id = ? and owner_id = ?
            order by created_at desc limit ?
            """,
            (tenant_id, owner_id, max(1, min(limit, 100))),
        ).fetchall()
    return [_from_row(row) for row in rows]


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _from_row(row: Any) -> AnalysisSessionResponse:
    return AnalysisSessionResponse.model_validate({
        "session_id": row["session_id"],
        "tenant_id": row["tenant_id"],
        "owner_id": row["owner_id"],
        "objective": row["objective"],
        "asset_ids": json.loads(row["asset_ids_json"]),
        "status": row["status"],
        "current_stage": row["current_stage"],
        "resume_token": row["resume_token"],
        "stages": json.loads(row["stages_json"]),
        "open_questions": json.loads(row["open_questions_json"]),
        "confirmations": json.loads(row["confirmations_json"]),
        "prd": json.loads(row["prd_json"]) if row["prd_json"] else None,
        "created_at": row["created_at"],
        "updated_at": row["updated_at"],
    })
