"""Tool-call audit persistence and aggregate observability metrics."""
from __future__ import annotations

import json
import math
import sqlite3
import uuid
from typing import Iterable

from app import database
from app.ticket_store import expire_pending_actions, format_time, init_ticket_store, utc_now


def record_tool_call(
    *,
    tool_name: str,
    operation: str,
    requires_approval: bool,
    status: str,
    actor_role: str,
    input_payload: dict,
    result: dict | None = None,
    error_message: str = "",
    duration_ms: float = 0.0,
    tenant_id: str = "legacy",
    owner_id: str = "legacy",
    actor_user: str = "anonymous",
) -> str:
    init_ticket_store()
    call_id = str(uuid.uuid4())
    now = format_time(utc_now())
    with database.connect() as conn:
        conn.execute(
            """
            insert into tool_call_logs (
                call_id, tool_name, operation, requires_approval, status, actor_role,
                tenant_id, owner_id, actor_user, input_json, result_json,
                error_message, duration_ms, created_at, updated_at
            ) values (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                call_id,
                tool_name,
                operation,
                int(requires_approval),
                status,
                actor_role,
                tenant_id,
                owner_id,
                actor_user,
                json.dumps(input_payload, ensure_ascii=False),
                json.dumps(result or {}, ensure_ascii=False),
                error_message[:500],
                round(duration_ms, 2),
                now,
                now,
            ),
        )
    return call_id


def update_tool_call(
    call_id: str,
    *,
    status: str,
    action_id: str = "",
    result: dict | None = None,
    error_message: str = "",
    duration_ms: float = 0.0,
) -> None:
    init_ticket_store()
    with database.connect() as conn:
        conn.execute(
            """
            update tool_call_logs
            set status = ?, action_id = case when ? = '' then action_id else ? end,
                result_json = ?, error_message = ?, duration_ms = ?, updated_at = ?
            where call_id = ?
            """,
            (
                status,
                action_id,
                action_id,
                json.dumps(result or {}, ensure_ascii=False),
                error_message[:500],
                round(duration_ms, 2),
                format_time(utc_now()),
                call_id,
            ),
        )


def list_tool_call_logs(
    limit: int = 50, *, tenant_id: str | None = None,
) -> list[dict[str, object]]:
    init_ticket_store()
    where = " where tenant_id = ?" if tenant_id is not None else ""
    params: list[object] = [tenant_id] if tenant_id is not None else []
    params.append(max(1, min(limit, 200)))
    with database.connect() as conn:
        rows = conn.execute(
            f"select * from tool_call_logs{where} order by created_at desc limit ?", params,
        ).fetchall()
    return [
        {
            "call_id": row["call_id"],
            "tool_name": row["tool_name"],
            "action_id": row["action_id"],
            "operation": row["operation"],
            "requires_approval": bool(row["requires_approval"]),
            "status": row["status"],
            "actor_role": row["actor_role"],
            "tenant_id": row["tenant_id"],
            "owner_id": row["owner_id"],
            "actor_user": row["actor_user"],
            "input": _load_json(row["input_json"]),
            "result": _load_json(row["result_json"]),
            "error_message": row["error_message"],
            "duration_ms": float(row["duration_ms"]),
            "created_at": row["created_at"],
        }
        for row in rows
    ]


def get_tool_metrics_summary(*, tenant_id: str | None = None) -> dict[str, object]:
    init_ticket_store()
    expire_pending_actions(tenant_id=tenant_id)
    where = " where tenant_id = ?" if tenant_id is not None else ""
    params = [tenant_id] if tenant_id is not None else []
    with database.connect() as conn:
        logs = conn.execute(
            f"select tool_name, status, duration_ms from tool_call_logs{where} order by created_at",
            params,
        ).fetchall()
        actions = conn.execute(
            f"select status, execution_count from pending_actions{where}", params,
        ).fetchall()
    statuses = _count_by(logs, "status")
    terminal = sum(statuses.get(item, 0) for item in ("succeeded", "failed"))
    decisions = sum(1 for row in actions if row["status"] in {"succeeded", "failed", "rejected"})
    approved = sum(1 for row in actions if row["status"] in {"succeeded", "failed"})
    durations = sorted(
        float(row["duration_ms"] or 0)
        for row in logs
        if row["status"] in {"succeeded", "failed"}
    )
    return {
        "total_calls": len(logs),
        "succeeded_calls": statuses.get("succeeded", 0),
        "pending_calls": statuses.get("pending", 0),
        "failed_calls": statuses.get("failed", 0),
        "rejected_calls": statuses.get("rejected", 0),
        "expired_calls": statuses.get("expired", 0),
        "success_rate": statuses.get("succeeded", 0) / terminal if terminal else 1.0,
        "approval_rate": approved / decisions if decisions else 0.0,
        "avg_duration_ms": _average(durations),
        "p95_duration_ms": _percentile(durations, 0.95),
        "exact_once_violations": sum(
            max(0, int(row["execution_count"]) - 1) for row in actions
        ),
        "by_tool": _count_by(logs, "tool_name"),
        "by_status": statuses,
    }


def _load_json(raw: str | None) -> object:
    try:
        return json.loads(raw or "{}")
    except (json.JSONDecodeError, TypeError):
        return {}


def _count_by(rows: Iterable[sqlite3.Row], column: str) -> dict[str, int]:
    result: dict[str, int] = {}
    for row in rows:
        key = str(row[column])
        result[key] = result.get(key, 0) + 1
    return result


def _average(values: list[float]) -> float:
    return round(sum(values) / len(values), 2) if values else 0.0


def _percentile(values: list[float], fraction: float) -> float:
    if not values:
        return 0.0
    return round(values[max(0, math.ceil(len(values) * fraction) - 1)], 2)
