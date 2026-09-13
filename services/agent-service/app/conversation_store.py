"""Tenant-scoped conversation turns and durable call-budget reservations."""

from __future__ import annotations

import json
import time
from dataclasses import dataclass
from uuid import uuid4

from app import database
from app.chat_observability_store import _refresh_historical_source_lifecycle
from app.config import CallLimits, get_call_limits, get_settings
from app.models import ChatResponse


class ConversationNotFound(LookupError):
    pass


class ConversationBusy(RuntimeError):
    pass


@dataclass(frozen=True)
class ConversationLease:
    conversation_id: str
    exchange_id: str
    tenant_id: str
    owner_id: str
    revision: int
    limits: CallLimits
    summary: str
    summary_through: int


def init_conversation_store() -> None:
    database.init_db()


def _get_conversation(conn, conversation_id: str, tenant_id: str, owner_id: str | None):
    owner_filter = " and owner_id = ?" if owner_id is not None else ""
    row = conn.execute(
        f"select * from conversations where conversation_id = ? and tenant_id = ?{owner_filter}",
        (conversation_id, tenant_id, owner_id) if owner_id is not None else (conversation_id, tenant_id),
    ).fetchone()
    if row is None:
        raise ConversationNotFound("Conversation not found.")
    return row


def begin_turn(conversation_id: str | None, *, tenant_id: str, owner_id: str | None,
               actor_user: str, exchange_id: str) -> ConversationLease:
    init_conversation_store()
    limits = get_call_limits()
    with database.connect() as conn:
        if conversation_id is None:
            conversation_id = str(uuid4())
            conn.execute("insert into conversations(conversation_id, tenant_id, owner_id) values (?, ?, ?)",
                         (conversation_id, tenant_id, actor_user))
        row = _get_conversation(conn, conversation_id, tenant_id, owner_id)
        now = time.time()
        reserved = CallLimits(min(limits.max_model_calls, max(0, 40 - row["model_calls"])),
                              min(limits.max_tool_calls, max(0, 30 - row["tool_calls"])))
        updated = conn.execute("""
            update conversations set lease_id = ?, lease_until = ?,
                model_calls = model_calls + ?, tool_calls = tool_calls + ?
            where conversation_id = ? and revision = ? and (lease_id is null or lease_until < ?)
        """, (exchange_id, now + get_settings().conversation_lease_seconds, reserved.max_model_calls, reserved.max_tool_calls,
              conversation_id, row["revision"], now))
        if updated.rowcount != 1:
            raise ConversationBusy("This conversation already has a turn in progress.")
    return ConversationLease(conversation_id, exchange_id, tenant_id, actor_user, row["revision"],
                             reserved, row["summary"], row["summary_through"])


def renew_turn(lease: ConversationLease) -> None:
    now = time.time()
    with database.connect() as conn:
        changed = conn.execute("""
            update conversations set lease_until = ?
            where conversation_id = ? and tenant_id = ? and revision = ?
              and lease_id = ? and lease_until >= ?
        """, (now + get_settings().conversation_lease_seconds, lease.conversation_id,
              lease.tenant_id, lease.revision, lease.exchange_id, now))
        if changed.rowcount != 1:
            raise ConversationBusy("Conversation lease expired or was replaced; retry this turn.")


def read_memory(lease: ConversationLease, *, older: bool = False) -> list[dict]:
    # The lease was obtained only after authorization. Never accept a client-provided scope here.
    with database.connect() as conn:
        if older:
            rows = conn.execute("""
                select turn, question, rewritten_question from conversation_turns
                where conversation_id = ? and tenant_id = ? and turn > ? and turn <= ?
                order by turn limit 6
            """, (lease.conversation_id, lease.tenant_id, lease.summary_through, max(0, lease.revision - 4))).fetchall()
        else:
            rows = conn.execute("""
                select turn, question, rewritten_question from conversation_turns
                where conversation_id = ? and tenant_id = ? and turn <= ? order by turn desc limit 4
            """, (lease.conversation_id, lease.tenant_id, lease.revision)).fetchall()[::-1]
    return [dict(row) for row in rows]


def finish_turn(lease: ConversationLease, *, question: str, rewritten_question: str,
                response: ChatResponse | None, model_calls: int, tool_calls: int,
                summary: str | None = None, summary_through: int | None = None) -> None:
    with database.connect() as conn:
        updated = conn.execute("""
            update conversations set revision = revision + ?, lease_id = null, lease_until = 0,
                model_calls = model_calls - ?, tool_calls = tool_calls - ?,
                summary = ?, summary_through = ?, updated_at = current_timestamp
            where conversation_id = ? and tenant_id = ? and revision = ? and lease_id = ? and lease_until >= ?
        """, (1 if response else 0, max(0, lease.limits.max_model_calls - model_calls),
              max(0, lease.limits.max_tool_calls - tool_calls),
              summary if response and summary is not None else lease.summary,
              summary_through if response and summary_through is not None else lease.summary_through,
              lease.conversation_id, lease.tenant_id, lease.revision, lease.exchange_id, time.time()))
        if updated.rowcount != 1:
            raise ConversationBusy("Conversation lease expired or was replaced; retry this turn.")
        if response is not None:
            conn.execute("""
                insert into conversation_turns(exchange_id, conversation_id, turn, tenant_id, owner_id,
                    question, rewritten_question, answer, sources_json) values (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (lease.exchange_id, lease.conversation_id, lease.revision + 1, lease.tenant_id, lease.owner_id,
                  question, rewritten_question, response.answer,
                  json.dumps([source.model_dump(mode="json") for source in response.sources], ensure_ascii=False)))


def get_conversation(conversation_id: str, *, tenant_id: str, owner_id: str | None) -> dict:
    init_conversation_store()
    with database.connect() as conn:
        row = _get_conversation(conn, conversation_id, tenant_id, owner_id)
        turns = conn.execute("""
            select exchange_id, turn, question, answer, sources_json, created_at
            from conversation_turns where conversation_id = ? and tenant_id = ? order by turn desc limit 50
        """, (conversation_id, tenant_id)).fetchall()[::-1]
    return {"conversation_id": conversation_id, "revision": row["revision"],
            "turns": [{"exchange_id": turn["exchange_id"], "turn": turn["turn"],
                       "question": turn["question"], "answer": turn["answer"],
                       "sources": _refresh_historical_source_lifecycle(json.loads(turn["sources_json"])),
                       "created_at": turn["created_at"]} for turn in turns]}


def purge_expired_conversations(conn, cutoff: str, batch_size: int, now: float) -> int:
    rows = conn.execute("""
        select conversation_id from conversations where updated_at < ?
          and (lease_id is null or lease_until < ?) order by updated_at limit ?
    """, (cutoff, now, batch_size)).fetchall()
    removed = 0
    for row in rows:
        identifier = row["conversation_id"]
        claim = str(uuid4())
        cursor = conn.execute("""
            update conversations set lease_id = ?, lease_until = ?
            where conversation_id = ? and updated_at < ? and (lease_id is null or lease_until < ?)
        """, (claim, now + 600, identifier, cutoff, now))
        if cursor.rowcount == 1:
            removed += conn.execute("delete from conversation_turns where conversation_id = ?", (identifier,)).rowcount
            removed += conn.execute("delete from conversations where conversation_id = ? and lease_id = ?", (identifier, claim)).rowcount
    return removed
