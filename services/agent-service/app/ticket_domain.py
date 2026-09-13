"""Ticket value objects and deterministic idempotency/expiry rules."""

import hashlib
import json
from dataclasses import dataclass, field
from datetime import datetime

TICKET_STATUSES = {"open", "in_progress", "resolved", "closed"}
TICKET_PRIORITIES = {"low", "medium", "high", "critical"}
FINAL_ACTION_STATUSES = {"succeeded", "failed", "rejected", "expired"}


@dataclass
class Ticket:
    ticket_id: str
    title: str
    description: str
    status: str
    priority: str
    assignee: str
    tenant_id: str = "legacy"
    owner_id: str = "legacy"
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
            "tenant_id": self.tenant_id,
            "owner_id": self.owner_id,
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
    tenant_id: str = "legacy"
    owner_id: str = "legacy"
    workspace_type: str = "personal"
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
            "tenant_id": self.tenant_id,
            "owner_id": self.owner_id,
            "workspace_type": self.workspace_type,
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


def build_idempotency_key(
    action_type: str, payload: dict, tenant_id: str = "legacy", owner_id: str = "legacy",
) -> str:
    raw = json.dumps(
        {"tenant_id": tenant_id, "owner_id": owner_id, "action_type": action_type, "payload": payload},
        ensure_ascii=False, sort_keys=True,
    )
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def _is_expired(raw: str, now: datetime) -> bool:
    if not raw:
        return False
    try:
        return datetime.fromisoformat(raw) <= now
    except ValueError:
        return False
