"""V3 persistence: tickets, approval state, and tool-call audit logs."""
from __future__ import annotations

import json
import sqlite3
import uuid
from datetime import UTC, datetime, timedelta

from app import database
from app.ticket_domain import (
    FINAL_ACTION_STATUSES as FINAL_ACTION_STATUSES,
)
from app.ticket_domain import (
    TICKET_PRIORITIES as TICKET_PRIORITIES,
)
from app.ticket_domain import (
    TICKET_STATUSES as TICKET_STATUSES,
)
from app.ticket_domain import (
    PendingAction as PendingAction,
)
from app.ticket_domain import (
    Ticket as Ticket,
)
from app.ticket_domain import (
    _is_expired as _is_expired,
)
from app.ticket_domain import (
    build_idempotency_key as build_idempotency_key,
)


def init_ticket_store() -> None:
    database.init_db()


def utc_now() -> datetime:
    return datetime.now(UTC)


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
    tenant_id: str = "legacy",
    owner_id: str = "legacy",
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
        tenant_id=tenant_id,
        owner_id=owner_id,
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
                source_document_ids, risk_level, tenant_id, owner_id, created_at, updated_at
            ) values (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
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
                ticket.tenant_id,
                ticket.owner_id,
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
    tenant_id: str | None = None,
    owner_id: str | None = None,
) -> list[Ticket]:
    init_ticket_store()
    clauses: list[str] = []
    params: list[object] = []
    if tenant_id is not None:
        clauses.append("tenant_id = ?")
        params.append(tenant_id)
    if owner_id is not None:
        clauses.append("owner_id = ?")
        params.append(owner_id)
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


def get_ticket(
    ticket_id: str, *, tenant_id: str | None = None, owner_id: str | None = None,
) -> Ticket | None:
    init_ticket_store()
    clauses = ["ticket_id = ?"]
    params: list[object] = [ticket_id]
    if tenant_id is not None:
        clauses.append("tenant_id = ?")
        params.append(tenant_id)
    if owner_id is not None:
        clauses.append("owner_id = ?")
        params.append(owner_id)
    with database.connect() as conn:
        row = conn.execute(
            f"select * from tickets where {' and '.join(clauses)}", params,
        ).fetchone()
    return _row_to_ticket(row) if row else None


def update_ticket_status(
    ticket_id: str, new_status: str, assignee: str | None = None,
    *, tenant_id: str | None = None, owner_id: str | None = None,
) -> Ticket | None:
    init_ticket_store()
    now = format_time(utc_now())
    clauses = ["ticket_id = ?"]
    scope_params: list[object] = [ticket_id]
    if tenant_id is not None:
        clauses.append("tenant_id = ?")
        scope_params.append(tenant_id)
    if owner_id is not None:
        clauses.append("owner_id = ?")
        scope_params.append(owner_id)
    where = " and ".join(clauses)
    with database.connect() as conn:
        if assignee is None:
            cursor = conn.execute(
                f"update tickets set status = ?, updated_at = ? where {where}",
                [new_status, now, *scope_params],
            )
        else:
            cursor = conn.execute(
                f"update tickets set status = ?, assignee = ?, updated_at = ? where {where}",
                [new_status, assignee.strip(), now, *scope_params],
            )
        if cursor.rowcount != 1:
            return None
    return get_ticket(ticket_id, tenant_id=tenant_id, owner_id=owner_id)


def delete_ticket(
    ticket_id: str, *, tenant_id: str | None = None, owner_id: str | None = None,
) -> bool:
    init_ticket_store()
    clauses = ["ticket_id = ?"]
    params: list[object] = [ticket_id]
    if tenant_id is not None:
        clauses.append("tenant_id = ?")
        params.append(tenant_id)
    if owner_id is not None:
        clauses.append("owner_id = ?")
        params.append(owner_id)
    with database.connect() as conn:
        return conn.execute(
            f"delete from tickets where {' and '.join(clauses)}", params,
        ).rowcount == 1





def create_pending_action(
    action_type: str,
    payload: dict,
    *,
    requested_by: str,
    tool_call_id: str,
    ttl_seconds: int = 900,
    idempotency_key: str = "",
    requested_by_user: str = "anonymous",
    tenant_id: str = "legacy",
    owner_id: str = "legacy",
    workspace_type: str = "personal",
) -> tuple[PendingAction, bool]:
    """Create a draft, or reuse an equivalent unresolved draft."""
    init_ticket_store()
    key = idempotency_key or build_idempotency_key(action_type, payload, tenant_id, owner_id)
    now_value = utc_now()
    now = format_time(now_value)
    expires_at = format_time(now_value + timedelta(seconds=ttl_seconds))
    with database.connect() as conn:
        conn.execute("begin immediate")
        existing = conn.execute(
            """
            select * from pending_actions
            where tenant_id = ? and owner_id = ? and idempotency_key = ?
              and status in ('pending', 'executing')
            order by created_at desc limit 1
            """,
            (tenant_id, owner_id, key),
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
                action_id, action_type, payload, status, tenant_id, owner_id, workspace_type,
                requested_by, requested_by_user,
                tool_call_id, idempotency_key, created_at, expires_at
            ) values (?, ?, ?, 'pending', ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                action_id,
                action_type,
                json.dumps(payload, ensure_ascii=False),
                tenant_id,
                owner_id,
                workspace_type,
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


def get_pending_action(
    action_id: str, *, conn: sqlite3.Connection | None = None,
    tenant_id: str | None = None,
) -> PendingAction | None:
    clauses = ["action_id = ?"]
    params: list[object] = [action_id]
    if tenant_id is not None:
        clauses.append("tenant_id = ?")
        params.append(tenant_id)
    query = f"select * from pending_actions where {' and '.join(clauses)}"
    if conn is not None:
        row = conn.execute(query, params).fetchone()
        return _row_to_action(row) if row else None
    init_ticket_store()
    with database.connect() as local_conn:
        row = local_conn.execute(query, params).fetchone()
    return _row_to_action(row) if row else None


def list_pending_actions(
    status: str | None = "pending", limit: int = 100, *, tenant_id: str | None = None,
) -> list[PendingAction]:
    init_ticket_store()
    expire_pending_actions(tenant_id=tenant_id)
    clauses: list[str] = []
    params: list[object] = []
    if tenant_id is not None:
        clauses.append("tenant_id = ?")
        params.append(tenant_id)
    if status:
        clauses.append("status = ?")
        params.append(status)
    where = f" where {' and '.join(clauses)}" if clauses else ""
    params.append(max(1, min(limit, 200)))
    with database.connect() as conn:
        rows = conn.execute(
            f"select * from pending_actions{where} order by created_at desc limit ?", params,
        ).fetchall()
    return [_row_to_action(row) for row in rows]


def claim_pending_action(
    action_id: str, resolved_by: str, *, tenant_id: str | None = None,
) -> tuple[PendingAction | None, bool]:
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
        row = get_pending_action(action_id, conn=conn, tenant_id=tenant_id)
        if row is None:
            return None, False
        if row.status != "pending":
            return row, False
        if _is_expired(row.expires_at, now_value):
            conn.execute(
                """
                update pending_actions
                set status = 'expired', resolved_by = ?, resolved_at = ?
                where action_id = ? and status = 'pending'
                """,
                (resolved_by, now, action_id),
            )
            return get_pending_action(action_id, conn=conn, tenant_id=tenant_id), False
        cursor = conn.execute(
            """
            update pending_actions
            set status = 'executing', resolved_by = ?, execution_count = execution_count + 1
            where action_id = ? and status = 'pending'
            """,
            (resolved_by, action_id),
        )
        if cursor.rowcount != 1:
            return get_pending_action(action_id, conn=conn, tenant_id=tenant_id), False
        return get_pending_action(action_id, conn=conn, tenant_id=tenant_id), True


def reject_pending_action(
    action_id: str, resolved_by: str, *, tenant_id: str | None = None,
) -> PendingAction | None:
    init_ticket_store()
    now_value = utc_now()
    now = format_time(now_value)
    with database.connect() as conn:
        conn.execute("begin immediate")
        row = get_pending_action(action_id, conn=conn, tenant_id=tenant_id)
        if row is None or row.status != "pending":
            return row
        status = "expired" if _is_expired(row.expires_at, now_value) else "rejected"
        conn.execute(
            """
            update pending_actions set status = ?, resolved_by = ?, resolved_at = ?
            where action_id = ? and status = 'pending'
            """,
            (status, resolved_by, now, action_id),
        )
        return get_pending_action(action_id, conn=conn, tenant_id=tenant_id)


def complete_pending_action(
    action_id: str,
    *,
    succeeded: bool,
    result: dict,
    error_message: str,
    duration_ms: float,
    tenant_id: str | None = None,
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
    return get_pending_action(action_id, tenant_id=tenant_id)


def get_ticket_summary(
    *, tenant_id: str | None = None, owner_id: str | None = None,
) -> dict[str, object]:
    init_ticket_store()
    clauses: list[str] = []
    params: list[object] = []
    if tenant_id is not None:
        clauses.append("tenant_id = ?")
        params.append(tenant_id)
    if owner_id is not None:
        clauses.append("owner_id = ?")
        params.append(owner_id)
    where = f" where {' and '.join(clauses)}" if clauses else ""
    with database.connect() as conn:
        total = int(conn.execute(f"select count(*) from tickets{where}", params).fetchone()[0])
        status_rows = conn.execute(
            f"select status, count(*) as count from tickets{where} group by status", params,
        ).fetchall()
        priority_rows = conn.execute(
            f"select priority, count(*) as count from tickets{where} group by priority", params,
        ).fetchall()
    return {
        "total_tickets": total,
        "by_status": {row["status"]: row["count"] for row in status_rows},
        "by_priority": {row["priority"]: row["count"] for row in priority_rows},
    }


def expire_pending_actions(*, tenant_id: str | None = None) -> int:
    """Move stale drafts out of the actionable queue and keep audit status aligned."""
    init_ticket_store()
    now = format_time(utc_now())
    with database.connect() as conn:
        tenant_clause = " and tenant_id = ?" if tenant_id is not None else ""
        params: list[object] = [now]
        if tenant_id is not None:
            params.append(tenant_id)
        rows = conn.execute(
            f"""
            select action_id, tool_call_id from pending_actions
            where status = 'pending' and expires_at != '' and expires_at <= ?
            {tenant_clause}
            """,
            params,
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
        tenant_id=row["tenant_id"],
        owner_id=row["owner_id"],
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
        tenant_id=row["tenant_id"],
        owner_id=row["owner_id"],
        workspace_type=row["workspace_type"],
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
