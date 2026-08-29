import base64
import hashlib
import hmac
import json
import os
import time
import unittest
from unittest.mock import patch

from fastapi.testclient import TestClient

from app.auth import JwtValidationError, decode_shared_jwt, validate_auth_configuration
from app.main import app
from app.models import ChatResponse
from app.retrievers import RetrievalScope


SECRET = "integration-test-shared-secret-32-bytes-minimum"


def encode_part(value: dict[str, object]) -> str:
    raw = json.dumps(value, separators=(",", ":"), sort_keys=True).encode("utf-8")
    return base64.urlsafe_b64encode(raw).rstrip(b"=").decode("ascii")


def access_token(**overrides: object) -> str:
    now = int(time.time())
    claims: dict[str, object] = {
        "iss": "enterprise-insight",
        "aud": "enterprise-insight-api",
        "sub": "user-123",
        "tenant_id": "tenant-123",
        "role": "operator",
        "workspace_type": "personal",
        "identity_version": 2,
        "username": "alice",
        "iat": now,
        "exp": now + 600,
        "jti": "token-123",
        "token_use": "access",
    }
    claims.update(overrides)
    header = encode_part({"alg": "HS256", "typ": "JWT"})
    payload = encode_part(claims)
    signature = hmac.new(
        SECRET.encode("utf-8"), f"{header}.{payload}".encode("ascii"), hashlib.sha256
    ).digest()
    encoded_signature = base64.urlsafe_b64encode(signature).rstrip(b"=").decode("ascii")
    return f"{header}.{payload}.{encoded_signature}"


class UnifiedAuthTests(unittest.TestCase):
    def setUp(self) -> None:
        self.env = patch.dict(
            os.environ,
            {
                "AGENT_AUTH_MODE": "jwt",
                "APP_ENV": "test",
                "SHARED_JWT_SECRET": SECRET,
                "APP_JWT_ISSUER": "enterprise-insight",
                "APP_JWT_AUDIENCE": "enterprise-insight-api",
            },
        )
        self.env.start()
        self.client = TestClient(app)

    def tearDown(self) -> None:
        self.env.stop()

    def test_validates_shared_claims_and_rejects_algorithm_or_expiry(self) -> None:
        claims = decode_shared_jwt(access_token())
        self.assertEqual(claims["sub"], "user-123")
        self.assertEqual(claims["tenant_id"], "tenant-123")
        self.assertEqual(claims["workspace_type"], "personal")

        with self.assertRaises(JwtValidationError):
            decode_shared_jwt(access_token(exp=1), now=100)

        parts = access_token().split(".")
        bad_header = encode_part({"alg": "none", "typ": "JWT"})
        with self.assertRaises(JwtValidationError):
            decode_shared_jwt(f"{bad_header}.{parts[1]}.{parts[2]}")

        with self.assertRaises(JwtValidationError):
            decode_shared_jwt(access_token(workspace_type="shared"))

    def test_chat_receives_server_validated_retrieval_scope(self) -> None:
        response_model = ChatResponse(answer="ok", sources=[])
        with (
            patch("app.routes.chat.answer_agentic_question", return_value=response_model) as answer,
            patch("app.routes.chat.safe_record_chat_metric", return_value=0),
        ):
            response = self.client.post(
                "/chat",
                headers={"Authorization": f"Bearer {access_token()}"},
                json={
                    "question": "跨视频预算要求是什么？",
                    "workflow_mode": "agentic",
                    "answer_mode": "local",
                    "retriever_mode": "hybrid",
                    "asset_ids": ["asset-1", "asset-2", "asset-1"],
                },
            )

        self.assertEqual(response.status_code, 200)
        answer.assert_called_once_with(
            "跨视频预算要求是什么？",
            answer_mode="local",
            retriever_mode="hybrid",
            actor_role="operator",
            actor_user="user-123",
            workspace_type="personal",
            retrieval_scope=RetrievalScope(
                tenant_id="tenant-123",
                owner_id="user-123",
                asset_ids=("asset-1", "asset-2"),
            ),
        )

    def test_team_chat_uses_tenant_wide_retrieval_scope(self) -> None:
        response_model = ChatResponse(answer="ok", sources=[])
        with (
            patch("app.routes.chat.answer_agentic_question", return_value=response_model) as answer,
            patch("app.routes.chat.safe_record_chat_metric", return_value=0),
        ):
            response = self.client.post(
                "/chat",
                headers={"Authorization": f"Bearer {access_token(workspace_type='team')}"},
                json={"question": "团队素材结论是什么？", "workflow_mode": "agentic"},
            )

        self.assertEqual(response.status_code, 200)
        self.assertIsNone(answer.call_args.kwargs["retrieval_scope"].owner_id)
        self.assertEqual(answer.call_args.kwargs["workspace_type"], "team")

    def test_jwt_mode_ignores_self_declared_identity_headers(self) -> None:
        response = self.client.get(
            "/documents",
            headers={"X-User-Role": "admin", "X-User-Id": "attacker"},
        )
        self.assertEqual(response.status_code, 401)
        self.assertEqual(response.headers.get("www-authenticate"), "Bearer")

    def test_production_rejects_development_auth_mode(self) -> None:
        with patch.dict(os.environ, {"APP_ENV": "production", "AGENT_AUTH_MODE": "development"}):
            with self.assertRaises(RuntimeError):
                validate_auth_configuration()


if __name__ == "__main__":
    unittest.main()
