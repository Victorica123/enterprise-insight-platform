"""Demo authorization boundary.

The header-based role is intentionally retained for the local prototype.  All
routers import the policy from this module so replacing it with JWT/OIDC later
does not require editing every endpoint.
"""
from fastapi import HTTPException


VALID_ROLES = frozenset({"viewer", "operator", "admin"})
WRITE_ROLES = frozenset({"operator", "admin"})
# 可访问审计/观测数据（问题原文、工具入参）的角色：与写角色同集合，语义单列。
OPERATOR_ROLES = WRITE_ROLES


def validate_actor_role(raw_role: str) -> str:
    role = raw_role.strip().lower()
    if role not in VALID_ROLES:
        raise HTTPException(status_code=403, detail="Unknown user role.")
    return role


def require_write_role(role: str) -> None:
    if role not in WRITE_ROLES:
        raise HTTPException(status_code=403, detail="Write permission is required.")


def require_operator_role(role: str) -> None:
    if role not in OPERATOR_ROLES:
        raise HTTPException(status_code=403, detail="Operator permission is required.")


def normalize_actor_user(raw_user: str) -> str:
    """用户标识统一小写去空白；缺省视为匿名（职责分离对匿名放行）。"""
    user = raw_user.strip().lower()
    return user or "anonymous"
