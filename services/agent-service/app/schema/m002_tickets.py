"""Baseline migration copied from the established domain store; append new versions."""

from app.schema.common import ensure_column


def migrate(conn) -> None:
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
    ensure_column(conn, "tickets", "tenant_id", "text not null default 'legacy'")
    ensure_column(conn, "tickets", "owner_id", "text not null default 'legacy'")
    conn.execute("create index if not exists idx_tickets_status on tickets(status)")
    conn.execute(
        "create index if not exists idx_tickets_scope on tickets(tenant_id, owner_id, created_at)"
    )
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
        "tenant_id": "text not null default 'legacy'",
        "owner_id": "text not null default 'legacy'",
        "workspace_type": "text not null default 'personal'",
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
        ensure_column(conn, "pending_actions", column, definition)
    conn.execute("create index if not exists idx_pending_actions_status on pending_actions(status)")
    conn.execute("create index if not exists idx_pending_actions_key on pending_actions(idempotency_key)")
    conn.execute(
        "create index if not exists idx_pending_actions_scope "
        "on pending_actions(tenant_id, status, created_at)"
    )
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
    for column, definition in {
        "tenant_id": "text not null default 'legacy'",
        "owner_id": "text not null default 'legacy'",
        "actor_user": "text not null default 'anonymous'",
    }.items():
        ensure_column(conn, "tool_call_logs", column, definition)
    conn.execute(
        "create index if not exists idx_tool_logs_scope "
        "on tool_call_logs(tenant_id, created_at)"
    )
