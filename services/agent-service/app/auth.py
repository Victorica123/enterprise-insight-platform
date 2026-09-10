"""Unified actor identity for the Agent Service.

Production accepts only the shared HS256 access JWT. Header identities remain
available exclusively in explicit development mode so existing offline demos and
tests stay deterministic while no production path trusts self-declared roles.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
import time
from dataclasses import dataclass
from functools import lru_cache
from typing import Any

from fastapi import Header, HTTPException, status

VALID_ROLES = frozenset({"viewer", "operator", "admin"})
VALID_WORKSPACE_TYPES = frozenset({"personal", "team"})
WRITE_ROLES = frozenset({"operator", "admin"})
OPERATOR_ROLES = WRITE_ROLES


@dataclass(frozen=True)
class ActorPrincipal:
    user_id: str
    tenant_id: str
    role: str
    username: str = ""
    token_id: str = ""
    auth_mode: str = "jwt"
    workspace_type: str = "team"

    @property
    def actor_user(self) -> str:
        if self.auth_mode == "development" and self.user_id == "legacy":
            return "anonymous"
        return normalize_actor_user(self.user_id)

    @property
    def retrieval_owner_id(self) -> str | None:
        # Imported V1 demo documents had no owner. Development mode deliberately
        # keeps that offline corpus visible. Team resources share the signed tenant
        # boundary; personal resources additionally keep the owner boundary.
        return None if self.auth_mode == "development" or self.workspace_type == "team" else self.user_id

    @property
    def resource_owner_id(self) -> str | None:
        return self.retrieval_owner_id


class JwtValidationError(ValueError):
    pass


def get_auth_mode() -> str:
    # Fail closed when deployment configuration is absent.  The compatibility
    # header path remains available only when development is explicitly set in
    # .env or the process environment.
    mode = os.getenv("AGENT_AUTH_MODE", "jwt").strip().lower()
    return mode if mode in {"development", "jwt"} else "jwt"


def validate_auth_configuration() -> None:
    mode = get_auth_mode()
    environment = os.getenv("APP_ENV", "development").strip().lower()
    if environment in {"production", "prod"} and mode != "jwt":
        raise RuntimeError("Production requires AGENT_AUTH_MODE=jwt.")
    if mode != "jwt":
        return
    algorithm = _jwt_algorithm()
    if algorithm == "HS256" and len(_jwt_secret()) < 32:
        raise RuntimeError("HS256 JWT mode requires SHARED_JWT_SECRET or APP_JWT_SECRET with at least 32 bytes.")
    if algorithm == "RS256" and not os.getenv("JWT_JWKS_URL", "").strip():
        raise RuntimeError("RS256 JWT mode requires JWT_JWKS_URL.")
    if algorithm not in {"HS256", "RS256"}:
        raise RuntimeError("JWT_ALGORITHM must be HS256 or RS256.")


def current_principal(
    authorization: str | None = Header(default=None),
    x_user_role: str = Header(default="viewer"),
    x_user_id: str = Header(default=""),
    x_tenant_id: str = Header(default="legacy"),
    x_workspace_type: str = Header(default="personal"),
) -> ActorPrincipal:
    if get_auth_mode() == "development":
        actor = normalize_actor_user(x_user_id)
        try:
            workspace_type = _workspace_type(x_workspace_type)
        except JwtValidationError as exc:
            raise HTTPException(status_code=403, detail=str(exc)) from exc
        return ActorPrincipal(
            user_id="legacy" if actor == "anonymous" else actor,
            tenant_id=x_tenant_id.strip() or "legacy",
            role=validate_actor_role(x_user_role),
            username=actor,
            auth_mode="development",
            workspace_type=workspace_type,
        )

    if authorization is None or not authorization.startswith("Bearer "):
        _unauthorized("Missing access token.")
    try:
        claims = decode_shared_jwt(authorization[7:])
    except JwtValidationError as exc:
        _unauthorized(str(exc))

    return ActorPrincipal(
        user_id=str(claims["sub"]),
        tenant_id=str(claims["tenant_id"]),
        role=str(claims["role"]),
        username=str(claims.get("username", "")),
        token_id=str(claims["jti"]),
        auth_mode="jwt",
        # V1 tokens did not carry workspace_type. Treating them as team is
        # fail-closed for self-publication while keeping read/retrieval compatible.
        workspace_type=str(claims.get("workspace_type", "team")),
    )


def decode_shared_jwt(token: str, *, now: int | None = None) -> dict[str, Any]:
    if _jwt_algorithm() == "RS256":
        claims = _decode_rs256_jwt(token)
        return _validate_claim_semantics(claims, now=now, time_validated=True)

    parts = token.split(".")
    if len(parts) != 3:
        raise JwtValidationError("Malformed access token.")
    encoded_header, encoded_payload, encoded_signature = parts
    header = _decode_json_part(encoded_header)
    claims = _decode_json_part(encoded_payload)
    if header.get("alg") != "HS256":
        raise JwtValidationError("Unsupported JWT algorithm.")

    secret = _jwt_secret()
    if len(secret) < 32:
        raise JwtValidationError("JWT verification is not configured.")
    signing_input = f"{encoded_header}.{encoded_payload}".encode("ascii")
    expected = hmac.new(secret.encode("utf-8"), signing_input, hashlib.sha256).digest()
    provided = _decode_base64url(encoded_signature)
    if not hmac.compare_digest(provided, expected):
        raise JwtValidationError("Invalid access token signature.")

    return _validate_claim_semantics(claims, now=now, time_validated=False)


def _validate_claim_semantics(
    claims: dict[str, Any], *, now: int | None, time_validated: bool
) -> dict[str, Any]:
    timestamp = int(time.time()) if now is None else now
    leeway = _read_non_negative_int("JWT_CLOCK_SKEW_SECONDS", 30)
    exp = _numeric_claim(claims, "exp")
    iat = _numeric_claim(claims, "iat")
    if not time_validated or now is not None:
        if exp <= timestamp - leeway:
            raise JwtValidationError("Access token has expired.")
        if iat > timestamp + leeway:
            raise JwtValidationError("Access token was issued in the future.")
        if "nbf" in claims and _numeric_claim(claims, "nbf") > timestamp + leeway:
            raise JwtValidationError("Access token is not active yet.")

    if claims.get("iss") != os.getenv("APP_JWT_ISSUER", "enterprise-insight"):
        raise JwtValidationError("Invalid access token issuer.")
    expected_audience = os.getenv("APP_JWT_AUDIENCE", "enterprise-insight-api")
    audiences = claims.get("aud")
    valid_audience = (
        audiences == expected_audience
        if isinstance(audiences, str)
        else isinstance(audiences, list) and expected_audience in audiences
    )
    if not valid_audience:
        raise JwtValidationError("Invalid access token audience.")
    if claims.get("token_use") != "access":
        raise JwtValidationError("JWT is not an access token.")

    for name in ("sub", "tenant_id", "jti"):
        if not isinstance(claims.get(name), str) or not claims[name].strip():
            raise JwtValidationError(f"Missing required claim: {name}.")
    role = str(claims.get("role", "")).strip().lower()
    if role not in VALID_ROLES:
        raise JwtValidationError("Invalid access token role.")
    claims["role"] = role
    if "workspace_type" in claims:
        claims["workspace_type"] = _workspace_type(str(claims["workspace_type"]))
    return claims


def _decode_rs256_jwt(token: str) -> dict[str, Any]:
    jwks_url = os.getenv("JWT_JWKS_URL", "").strip()
    if not jwks_url:
        raise JwtValidationError("JWT verification is not configured.")
    try:
        import jwt

        signing_key = _jwk_client(jwks_url).get_signing_key_from_jwt(token)
        decoded = jwt.decode(
            token,
            signing_key.key,
            algorithms=["RS256"],
            issuer=os.getenv("APP_JWT_ISSUER", "enterprise-insight"),
            audience=os.getenv("APP_JWT_AUDIENCE", "enterprise-insight-api"),
            leeway=_read_non_negative_int("JWT_CLOCK_SKEW_SECONDS", 30),
            options={"require": ["exp", "iat", "sub", "tenant_id", "jti"]},
        )
    except Exception as exc:
        raise JwtValidationError("Invalid or expired access token.") from exc
    if not isinstance(decoded, dict):
        raise JwtValidationError("Malformed JWT object.")
    return decoded


@lru_cache(maxsize=8)
def _jwk_client(jwks_url: str):
    try:
        from jwt import PyJWKClient
    except ImportError as exc:  # pragma: no cover - deployment dependency guard
        raise RuntimeError("RS256 JWT verification requires PyJWT[crypto].") from exc
    return PyJWKClient(jwks_url, cache_keys=True, lifespan=300)


def validate_actor_role(raw_role: str) -> str:
    role = raw_role.strip().lower()
    if role not in VALID_ROLES:
        raise HTTPException(status_code=403, detail="Unknown user role.")
    return role


def _workspace_type(raw_workspace_type: str) -> str:
    workspace_type = raw_workspace_type.strip().lower()
    if workspace_type not in VALID_WORKSPACE_TYPES:
        raise JwtValidationError("Invalid workspace type.")
    return workspace_type


def require_write_role(role: str) -> None:
    if role not in WRITE_ROLES:
        raise HTTPException(status_code=403, detail="Write permission is required.")


def require_operator_role(role: str) -> None:
    if role not in OPERATOR_ROLES:
        raise HTTPException(status_code=403, detail="Operator permission is required.")


def normalize_actor_user(raw_user: str) -> str:
    user = raw_user.strip().lower()
    return user or "anonymous"


def _jwt_secret() -> str:
    return os.getenv("SHARED_JWT_SECRET") or os.getenv("APP_JWT_SECRET", "")


def _jwt_algorithm() -> str:
    return os.getenv("JWT_ALGORITHM", "HS256").strip().upper()


def _decode_json_part(encoded: str) -> dict[str, Any]:
    try:
        value = json.loads(_decode_base64url(encoded).decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError, ValueError) as exc:
        raise JwtValidationError("Malformed JWT JSON.") from exc
    if not isinstance(value, dict):
        raise JwtValidationError("Malformed JWT object.")
    return value


def _decode_base64url(encoded: str) -> bytes:
    try:
        padding = "=" * (-len(encoded) % 4)
        return base64.urlsafe_b64decode(encoded + padding)
    except (ValueError, TypeError) as exc:
        raise JwtValidationError("Malformed JWT encoding.") from exc


def _numeric_claim(claims: dict[str, Any], name: str) -> int:
    value = claims.get(name)
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise JwtValidationError(f"Missing or invalid claim: {name}.")
    return int(value)


def _read_non_negative_int(name: str, default: int) -> int:
    try:
        return max(0, int(os.getenv(name, str(default))))
    except ValueError:
        return default


def _unauthorized(detail: str) -> None:
    raise HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail=detail,
        headers={"WWW-Authenticate": "Bearer"},
    )
