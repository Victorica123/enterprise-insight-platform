"""Bounded retention jobs for transcript evidence and operational audit records."""

from __future__ import annotations

import asyncio
import logging
from contextlib import suppress
from datetime import UTC, datetime, timedelta

from app import database
from app.config import get_settings
from app.conversation_store import init_conversation_store, purge_expired_conversations
from app.graph_store import rebuild_graph_scope

logger = logging.getLogger(__name__)


def retention_enabled() -> bool:
    return get_settings().retention_enabled


def validate_retention_configuration() -> None:
    errors = [error for error in get_settings().errors if error.startswith("RETENTION_")]
    if retention_enabled() and errors:
        raise RuntimeError("; ".join(errors))


def run_retention_once(now: datetime | None = None) -> dict[str, int]:
    """Delete one bounded batch; callers may run it repeatedly for a backlog."""
    if not retention_enabled():
        return {"video_documents": 0, "audit_records": 0}
    current = now or datetime.now(UTC)
    transcript_cutoff = (current - timedelta(days=get_settings().retention_transcript_days)).isoformat(
        timespec="seconds"
    )
    audit_cutoff = (current - timedelta(days=get_settings().retention_audit_days)).isoformat(
        timespec="seconds"
    )
    batch_size = min(1000, get_settings().retention_batch_size)
    audit_deleted = 0
    init_conversation_store()

    with database.connect() as conn:
        documents = conn.execute(
            """
            select id, tenant_id, owner_id from documents
            where source_type = 'video' and created_at < ?
            order by created_at asc limit ?
            """,
            (transcript_cutoff, batch_size),
        ).fetchall()
        document_ids = [str(row["id"]) for row in documents]
        if document_ids:
            placeholders = ",".join("?" for _ in document_ids)
            conn.execute(
                f"delete from ingestion_receipts where document_id in ({placeholders})", document_ids
            )
            conn.execute(f"delete from chunks where document_id in ({placeholders})", document_ids)
            conn.execute(f"delete from documents where id in ({placeholders})", document_ids)
            database.bump_content_revision(conn)
            for tenant_id, owner_id in sorted(
                {(str(row["tenant_id"]), str(row["owner_id"])) for row in documents}
            ):
                rebuild_graph_scope(conn=conn, tenant_id=tenant_id, owner_id=owner_id)

        audit_deleted += _delete_by_age(conn, "chat_metrics", "id", "created_at", audit_cutoff, batch_size)
        audit_deleted += _delete_by_age(conn, "chat_logs", "log_id", "created_at", audit_cutoff, batch_size)
        audit_deleted += _delete_by_age(conn, "tool_call_logs", "call_id", "created_at", audit_cutoff, batch_size)
        audit_deleted += _delete_by_age(
            conn, "analysis_audit_events", "event_id", "created_at", audit_cutoff, batch_size
        )
        audit_deleted += _delete_final_actions(conn, audit_cutoff, batch_size)
        audit_deleted += purge_expired_conversations(conn, audit_cutoff, batch_size, current.timestamp())

    result = {"video_documents": len(document_ids), "audit_records": audit_deleted}
    if document_ids or audit_deleted:
        logger.info("retention_batch_applied counts=%s", result)
    return result


async def retention_loop() -> None:
    interval = get_settings().retention_scan_interval_seconds
    while True:
        try:
            await asyncio.to_thread(run_retention_once)
        except asyncio.CancelledError:
            raise
        except Exception:
            logger.exception("retention_batch_failed")
        await asyncio.sleep(interval)


async def stop_retention_task(task: asyncio.Task[None] | None) -> None:
    if task is None:
        return
    task.cancel()
    with suppress(asyncio.CancelledError):
        await task


def _delete_by_age(conn, table: str, id_column: str, time_column: str, cutoff: str, limit: int) -> int:
    rows = conn.execute(
        f"select {id_column} from {table} where {time_column} < ? order by {time_column} asc limit ?",
        (cutoff, limit),
    ).fetchall()
    ids = [row[id_column] for row in rows]
    if not ids:
        return 0
    placeholders = ",".join("?" for _ in ids)
    conn.execute(f"delete from {table} where {id_column} in ({placeholders})", ids)
    return len(ids)


def _delete_final_actions(conn, cutoff: str, limit: int) -> int:
    rows = conn.execute(
        """
        select action_id from pending_actions
        where status in ('succeeded', 'failed', 'rejected', 'expired')
          and coalesce(resolved_at, created_at) < ?
        order by created_at asc limit ?
        """,
        (cutoff, limit),
    ).fetchall()
    ids = [row["action_id"] for row in rows]
    if not ids:
        return 0
    placeholders = ",".join("?" for _ in ids)
    conn.execute(f"delete from pending_actions where action_id in ({placeholders})", ids)
    return len(ids)
