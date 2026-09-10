"""Shared request context passed between Agent Service boundaries.

The context is derived from the server-validated principal.  It is not a
replacement for authorization checks: each repository/tool still validates the
scope at its own boundary.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass

from app.auth import ActorPrincipal


@dataclass(frozen=True)
class RequestContext:
    tenant_id: str
    owner_id: str | None
    actor_user: str
    role: str
    workspace_type: str
    auth_mode: str
    trace_id: str | None = None

    @classmethod
    def from_principal(cls, principal: ActorPrincipal) -> RequestContext:
        return cls(
            tenant_id=principal.tenant_id,
            owner_id=principal.retrieval_owner_id,
            actor_user=principal.actor_user,
            role=principal.role,
            workspace_type=principal.workspace_type,
            auth_mode=principal.auth_mode,
        )

    def retrieval_scope(self, asset_ids: Iterable[str] = ()):  # pragma: no cover - typed adapter
        """Build a scope only after the principal has been validated by FastAPI."""
        from .retrieval import RetrievalScope

        return RetrievalScope(
            tenant_id=self.tenant_id,
            owner_id=self.owner_id,
            asset_ids=tuple(dict.fromkeys(asset_ids)),
        )
