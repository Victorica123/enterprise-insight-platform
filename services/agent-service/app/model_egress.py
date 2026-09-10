"""Tenant-scoped, fail-closed gate for external model data egress."""

from __future__ import annotations

import os
from contextvars import ContextVar, Token

_TENANT: ContextVar[str | None] = ContextVar("model_egress_tenant", default=None)


class ModelEgressDenied(RuntimeError):
    pass


def bind_model_egress_tenant(tenant_id: str) -> Token[str | None]:
    return _TENANT.set(tenant_id.strip())


def reset_model_egress_tenant(token: Token[str | None]) -> None:
    _TENANT.reset(token)


def is_model_egress_allowed(tenant_id: str | None = None) -> bool:
    tenant = (tenant_id if tenant_id is not None else _TENANT.get()) or ""
    tenant = tenant.strip()
    environment = os.getenv("APP_ENV", "development").strip().lower()
    policy = os.getenv(
        "MODEL_EGRESS_POLICY",
        "allowlist" if environment in {"production", "prod"} else "allow",
    ).strip().lower()
    allowed = {
        value.strip()
        for value in os.getenv("MODEL_EGRESS_ALLOWED_TENANTS", "").split(",")
        if value.strip()
    }
    # Production never accepts a global allow switch: each workspace must be named.
    if environment in {"production", "prod"}:
        return bool(tenant) and tenant in allowed
    if policy == "allow":
        return True
    if policy == "allowlist":
        return bool(tenant) and tenant in allowed
    return False


def require_model_egress_allowed() -> None:
    tenant = _TENANT.get()
    if not is_model_egress_allowed(tenant):
        raise ModelEgressDenied(
            f"External model data egress is not approved for tenant {tenant or '<unbound>'}."
        )
