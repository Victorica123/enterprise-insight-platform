"""V3 persistence: tickets, approval state, and tool-call audit logs."""
from __future__ import annotations

import hashlib
import json
import math
from pathlib import Path
import sqlite3
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Iterable

from app import database


TICKET_STATUSES = {"open", "in_progress", "resolved", "closed"}
TICKET_PRIORITIES = {"low", "medium", "high", "critical"}
FINAL_ACTION_STATUSES = {"succeeded", "failed", "rejected", "expired"}
_INITIALIZED_DB_PATH: Path | None = None


@dataclass
class Ticket:
    ticket_id: str
    title: str
    description: str
    status: str
    priority: str
    assignee: str
    source_document_ids: list[str] = field(default_factory=list)
    risk_level: str = ""
    created_at: str = ""
    updated_at: str = ""

    def to_dict(self) -> dict[str, object]:
        return {
            "ticket_id": self.ticket_id,
            "title": self.title,
            "description": self.description,
            "status": self.status,
            "priority": self.priority,
            "assignee": self.assignee,
            "source_document_ids": self.source_document_ids,
            "risk_level": self.risk_level,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
        }


@dataclass
class PendingAction:
    action_id: str
    action_type: str
    payload: dict
    status: str
    requested_by: str = "operator"
    requested_by_user: str = "anonymous"
    resolved_by: str = ""
    tool_call_id: str = ""
    idempotency_key: str = ""
    result: dict = field(default_factory=dict)
    error_message: str = ""
    duration_ms: float = 0.0
    execution_count: int = 0
    created_at: str = ""
    expires_at: str = ""
    resolved_at: str = ""

    def to_dict(self) -> dict[str, object]:
        return {
            "action_id": self.action_id,
            "action_type": self.action_type,
            "payload": self.payload,
            "status": self.status,
            "requested_by": self.requested_by,
            "requested_by_user": self.requested_by_user,
            "resolved_by": self.resolved_by,
            "result": self.result,
            "error_message": self.error_message,
            "duration_ms": self.duration_ms,
            "execution_count": self.execution_count,
            "created_at": self.created_at,
            "expires_at": self.expires_at,
            "resolved_at": self.resolved_at,
        }


def init_ticket_store() -> None:
    global _INITIALIZED_DB_PATH
    current_path = database.DB_PATH.resolve()
    if _INITIALIZED_DB_PATH == current_path and current_path.exists():
        return
    database.DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    with database.connect() as conn:
        conn.execute(
            """
            create table if not exists tickets (
                ticket_id text primary key,
                title text not null,
                description text not null,
                status text not null default 'open',
                priority text not null default 'medium',
                assignee text not null default '',
                source_document_ids text not null default '[]',
                risk_level text not null default '',
                created_at text not null,
                updated_at text not null
            )
            """
        )
        conn.execute("create index if not exists idx_tickets_status on tickets(status)")
        conn.execute(
            """
            create table if not exists pending_actions (
                action_id text primary key,
                action_type text not null,
                payload text not null default '{}',
                status text not null default 'pending',
                created_at text not null,
                resolved_at text
            )
            """
        )
        pending_columns = {
            "requested_by": "text not null default 'operator'",
            "requested_by_user": "text not null default 'anonymous'",
            "resolved_by": "text not null default ''",
            "tool_call_id": "text not null default ''",
            "idempotency_key": "text not null default ''",
            "result": "text not null default '{}'",
            "error_message": "text not null default ''",
            "duration_ms": "real not null default 0",
            "execution_count": "integer not null default 0",
            "expires_at": "text not null default ''",
        }
        for column, definition in pending_columns.items():
            database.ensure_column(conn, "pending_actions", column, definition)
        conn.execute("create index if not exists idx_pending_actions_status on pending_actions(status)")
        conn.execute("create index if not exists idx_pending_actions_key on pending_actions(idempotency_key)")
        conn.execute(
            """
            create table if not exists tool_call_logs (
                call_id text primary key,
                tool_name text not null,
                action_id text not null default '',
                operation text not null,
                requires_approval integer not null,
                status text not null,
                actor_role text not null,
                input_json text not null default '{}',
                result_json text not null default '{}',
                error_message text not null default '',
                duration_ms real not null default 0,
                created_at text not null,
                updated_at text not null
            )
            """
        )
        conn.execute("create index if not exists idx_tool_logs_created on tool_call_logs(created_at)")
        conn.execute("create index if not exists idx_tool_logs_status on tool_call_logs(status)")
    _INITIALIZED_DB_PATH = current_path


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def format_time(value: datetime) -> str:
    return value.isoformat(timespec="seconds")


def create_ticket(
    title: str,
    description: str,
    status: str = "open",
    priority: str = "medium",
    assignee: str = "",
    source_document_ids: list[str] | None = None,
    risk_level: str = "",
) -> Ticket:
    init_ticket_store()
    now = format_time(utc_now())
    ticket = Ticket(
        ticket_id=str(uuid.uuid4()),
        title=title.strip(),
        description=description.strip(),
        status=status,
        priority=priority,
        assignee=assignee.strip(),
        source_document_ids=source_document_ids or [],
        risk_level=risk_level.strip(),
        created_at=now,
        updated_at=now,
    )
    with database.connect() as conn:
        conn.execute(
            """
            insert into tickets (
                ticket_id, title, description, status, priority, assignee,
                source_document_ids, risk_level, created_at, updated_at
            ) values (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                ticket.ticket_id,
                ticket.title,
                ticket.description,
                ticket.status,
                ticket.priority,
                ticket.assignee,
                json.dumps(ticket.source_document_ids, ensure_ascii=False),
                ticket.risk_level,
                now,
                now,
            ),
        )
    return ticket


def list_tickets(
    status: str | None = None,
    priority: str | None = None,
    keyword: str = "",
    limit: int = 100,
) -> list[Ticket]:
    init_ticket_store()
    clauses: list[str] = []
    params: list[object] = []
    if status:
        clauses.append("status = ?")
        params.append(status)
    if priority:
        clauses.append("priority = ?")
        params.append(priority)
    if keyword:
        clauses.append("(lower(title) like ? or lower(description) like ?)")
        pattern = f"%{keyword.lower()}%"
        params.extend([pattern, pattern])
    where = f" where {' and '.join(clauses)}" if clauses else ""
    params.append(max(1, min(limit, 200)))
    with database.connect() as conn:
        rows = conn.execute(
            f"select * from tickets{where} order by created_at desc limit ?", params
        ).fetchall()
    return [_row_to_ticket(row) for row in rows]


def get_ticket(ticket_id: str) -> Ticket | None:
    init_ticket_store()
    with database.connect() as conn:
        row = conn.execute("select * from tickets where ticket_id = ?", (ticket_id,)).fetchone()
    return _row_to_ticket(row) if row else None


def update_ticket_status(ticket_id: str, new_status: str, assignee: str | None = None) -> Ticket | None:
    init_ticket_store()
    now = format_time(utc_now())
    with database.connect() as conn:
        if assignee is None:
            cursor = conn.execute(
                "update tickets set status = ?, updated_at = ? where ticket_id = ?",
                (new_status, now, ticket_id),
            )
        else:
            cursor = conn.execute(
                "update tickets set status = ?, assignee = ?, updated_at = ? where ticket_id = ?",
                (new_status, assignee.strip(), now, ticket_id),
            )
        if cursor.rowcount != 1:
            return None
    return get_ticket(ticket_id)


def delete_ticket(ticket_id: str) -> bool:
    init_ticket_store()
    with database.connect() as conn:
        return conn.execute("delete from tickets where ticket_id = ?", (ticket_id,)).rowcount == 1


def build_idempotency_key(action_type: str, payload: dict) -> str:
    raw = json.dumps({"action_type": action_type, "payload": payload}, ensure_ascii=False, sort_keys=True)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def create_pending_action(
    action_type: str,
    payload: dict,
    *,
    requested_by: str,
    tool_call_id: str,
    ttl_seconds: int = 900,
    idempotency_key: str = "",
    requested_by_user: str = "anonymous",
) -> tuple[PendingAction, bool]:
    """Create a draft, or reuse an equivalent unresolved draft."""
    init_ticket_store()
    key = idempotency_key or build_idempotency_key(action_type, payload)
    now_value = utc_now()
    now = format_time(now_value)
    expires_at = format_time(now_value + timedelta(seconds=ttl_seconds))
    with database.connect() as conn:
        conn.execute("begin immediate")
        existing = conn.execute(
            """
            select * from pending_actions
            where idempotency_key = ? and status in ('pending', 'executing')
            order by created_at desc limit 1
            """,
            (key,),
        ).fetchone()
        if existing and (
            existing["status"] == "executing" or not _is_expired(existing["expires_at"], now_value)
        ):
            return _row_to_action(existing), True
        if existing and existing["status"] == "pending":
            conn.execute(
                "update pending_actions set status = 'expired', resolved_at = ? where action_id = ?",
                (now, existing["action_id"]),
            )
            conn.execute(
                """
                update tool_call_logs set status = 'expired', updated_at = ?
                where call_id = ? and status in ('pending', 'preparing')
                """,
                (now, existing["tool_call_id"]),
            )

        action_id = str(uuid.uuid4())
        conn.execute(
            """
            insert into pending_actions (
                action_id, action_type, payload, status, requested_by, requested_by_user,
                tool_call_id, idempotency_key, created_at, expires_at
            ) values (?, ?, ?, 'pending', ?, ?, ?, ?, ?, ?)
            """,
            (
                action_id,
                action_type,
                json.dumps(payload, ensure_ascii=False),
                requested_by,
                requested_by_user,
                tool_call_id,
                key,
                now,
                expires_at,
            ),
        )
        action = get_pending_action(action_id, conn=conn)
    if action is None:
        raise RuntimeError("Pending action was not persisted.")
    return action, False


def get_pending_action(action_id: str, *, conn: sqlite3.Connection | None = None) -> PendingAction | None:
    if conn is not None:
        row = conn.execute("select * from pending_actions where action_id = ?", (action_id,)).fetchone()
        return _row_to_action(row) if row else None
    init_ticket_store()
    with database.connect() as local_conn:
        row = local_conn.execute("select * from pending_actions where action_id = ?", (action_id,)).fetchone()
    return _row_to_action(row) if row else None


def list_pending_actions(status: str | None = "pending", limit: int = 100) -> list[PendingAction]:
    init_ticket_store()
    expire_pending_actions()
    with database.connect() as conn:
        if status:
            rows = conn.execute(
                "select * from pending_actions where status = ? order by created_at desc limit ?",
                (status, max(1, min(limit, 200))),
            ).fetchall()
        else:
            rows = conn.execute(
                "select * from pending_actions order by created_at desc limit ?",
                (max(1, min(limit, 200)),),
            ).fetchall()
    return [_row_to_action(row) for row in rows]


def claim_pending_action(action_id: str, resolved_by: str) -> tuple[PendingAction | None, bool]:
    """Atomically move a pending action to executing.

    The boolean is the ownership result. Returning an ``executing`` row alone
    is not sufficient: it may have been claimed by another request, which must
    never be allowed to run the side effect again.
    """
    init_ticket_store()
    now_value = utc_now()
    now = format_time(now_value)
    with database.connect() as conn:
        conn.execute("begin immediate")
        row = conn.execute("select * from pending_actions where action_id = ?", (action_id,)).fetchone()
        if row is None:
            return None, False
        if row["status"] != "pending":
            return _row_to_action(row), False
        if _is_expired(row["expires_at"], now_value):
            conn.execute(
                """
                update pending_actions
                set status = 'expired', resolved_by = ?, resolved_at = ?
                where action_id = ? and status = 'pending'
                """,
                (resolved_by, now, action_id),
            )
            return get_pending_action(action_id, conn=conn), False
        cursor = conn.execute(
            """
            update pending_actions
            set status = 'executing', resolved_by = ?, execution_count = execution_count + 1
            where action_id = ? and status = 'pending'
            """,
            (resolved_by, action_id),
        )
        if cursor.rowcount != 1:
            return get_pending_action(action_id, conn=conn), False
        return get_pending_action(action_id, conn=conn), True


def reject_pending_action(action_id: str, resolved_by: str) -> PendingAction | None:
    init_ticket_store()
    now_value = utc_now()
    now = format_time(now_value)
    with database.connect() as conn:
        conn.execute("begin immediate")
        row = conn.execute("select * from pending_actions where action_id = ?", (action_id,)).fetchone()
        if row is None or row["status"] != "pending":
            return _row_to_action(row) if row else None
        status = "expired" if _is_expired(row["expires_at"], now_value) else "rejected"
        conn.execute(
            """
            update pending_actions set status = ?, resolved_by = ?, resolved_at = ?
            where action_id = ? and status = 'pending'
            """,
            (status, resolved_by, now, action_id),
        )
        return get_pending_action(action_id, conn=conn)


def complete_pending_action(
    action_id: str,
    *,
    succeeded: bool,
    result: dict,
    error_message: str,
    duration_ms: float,
) -> PendingAction | None:
    init_ticket_store()
    status = "succeeded" if succeeded else "failed"
    now = format_time(utc_now())
    with database.connect() as conn:
        conn.execute(
            """
            update pending_actions
            set status = ?, result = ?, error_message = ?, duration_ms = ?, resolved_at = ?
            where action_id = ? and status = 'executing'
            """,
            (
                status,
                json.dumps(result, ensure_ascii=False),
                error_message[:500],
                round(duration_ms, 2),
                now,
                action_id,
            ),
        )
    return get_pending_action(action_id)


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
) -> str:
    init_ticket_store()
    call_id = str(uuid.uuid4())
    now = format_time(utc_now())
    with database.connect() as conn:
        conn.execute(
            """
            insert into tool_call_logs (
                call_id, tool_name, operation, requires_approval, status, actor_role,
                input_json, result_json, error_message, duration_ms, created_at, updated_at
            ) values (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                call_id,
                tool_name,
                operation,
                int(requires_approval),
                status,
                actor_role,
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


def list_tool_call_logs(limit: int = 50) -> list[dict[str, object]]:
    init_ticket_store()
    with database.connect() as conn:
        rows = conn.execute(
            "select * from tool_call_logs order by created_at desc limit ?",
            (max(1, min(limit, 200)),),
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
            "input": _load_json(row["input_json"]),
            "result": _load_json(row["result_json"]),
            "error_message": row["error_message"],
            "duration_ms": float(row["duration_ms"]),
            "created_at": row["created_at"],
        }
        for row in rows
    ]


def get_tool_metrics_summary() -> dict[str, object]:
    init_ticket_store()
    expire_pending_actions()
    with database.connect() as conn:
        logs = conn.execute(
            "select tool_name, status, duration_ms from tool_call_logs order by created_at"
        ).fetchall()
        actions = conn.execute("select status, execution_count from pending_actions").fetchall()
    statuses = _count_by(logs, "status")
    terminal = sum(statuses.get(item, 0) for item in ("succeeded", "failed"))
    decisions = sum(1 for row in actions if row["status"] in {"succeeded", "failed", "rejected"})
    approved = sum(1 for row in actions if row["status"] in {"succeeded", "failed"})
    durations = sorted(float(row["duration_ms"] or 0) for row in logs if row["status"] in {"succeeded", "failed"})
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
        "exact_once_violations": sum(max(0, int(row["execution_count"]) - 1) for row in actions),
        "by_tool": _count_by(logs, "tool_name"),
        "by_status": statuses,
    }


def get_ticket_summary() -> dict[str, object]:
    init_ticket_store()
    with database.connect() as conn:
        total = int(conn.execute("select count(*) from tickets").fetchone()[0])
        status_rows = conn.execute("select status, count(*) as count from tickets group by status").fetchall()
        priority_rows = conn.execute("select priority, count(*) as count from tickets group by priority").fetchall()
    return {
        "total_tickets": total,
        "by_status": {row["status"]: row["count"] for row in status_rows},
        "by_priority": {row["priority"]: row["count"] for row in priority_rows},
    }


def expire_pending_actions() -> int:
    """Move stale drafts out of the actionable queue and keep audit status aligned."""
    init_ticket_store()
    now = format_time(utc_now())
    with database.connect() as conn:
        rows = conn.execute(
            """
            select action_id, tool_call_id from pending_actions
            where status = 'pending' and expires_at != '' and expires_at <= ?
            """,
            (now,),
        ).fetchall()
        if not rows:
            return 0
        action_ids = [row["action_id"] for row in rows]
        placeholders = ",".join("?" for _ in action_ids)
        conn.execute(
            f"update pending_actions set status = 'expired', resolved_at = ? where action_id in ({placeholders})",
            [now, *action_ids],
        )
        for row in rows:
            conn.execute(
                """
                update tool_call_logs set status = 'expired', updated_at = ?
                where call_id = ? and status in ('pending', 'preparing')
                """,
                (now, row["tool_call_id"]),
            )
    return len(rows)


def _row_to_ticket(row: sqlite3.Row) -> Ticket:
    return Ticket(
        ticket_id=row["ticket_id"],
        title=row["title"],
        description=row["description"],
        status=row["status"],
        priority=row["priority"],
        assignee=row["assignee"],
        source_document_ids=_load_json(row["source_document_ids"], fallback=[]),
        risk_level=row["risk_level"],
        created_at=row["created_at"],
        updated_at=row["updated_at"],
    )


def _row_to_action(row: sqlite3.Row) -> PendingAction:
    return PendingAction(
        action_id=row["action_id"],
        action_type=row["action_type"],
        payload=_load_json(row["payload"]),
        status=row["status"],
        requested_by=row["requested_by"],
        requested_by_user=row["requested_by_user"] if "requested_by_user" in row.keys() else "anonymous",
        resolved_by=row["resolved_by"],
        tool_call_id=row["tool_call_id"],
        idempotency_key=row["idempotency_key"],
        result=_load_json(row["result"]),
        error_message=row["error_message"],
        duration_ms=float(row["duration_ms"]),
        execution_count=int(row["execution_count"]),
        created_at=row["created_at"],
        expires_at=row["expires_at"],
        resolved_at=row["resolved_at"] or "",
    )


def _load_json(raw: str | None, fallback: object | None = None):
    try:
        return json.loads(raw or "{}")
    except (json.JSONDecodeError, TypeError):
        return {} if fallback is None else fallback


def _is_expired(raw: str, now: datetime) -> bool:
    if not raw:
        return False
    try:
        return datetime.fromisoformat(raw) <= now
    except ValueError:
        return False


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
