import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from app import database
from app.main import app
from app.retrievers import clear_chunk_cache
from fastapi.testclient import TestClient

from tests.test_unified_auth import SECRET, access_token


class WorkspaceCollaborationApiTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.original_path = database.DB_PATH
        database.DB_PATH = Path(self.temp.name) / "workspace.sqlite3"
        database._INITIALIZED_DB_PATH = None
        clear_chunk_cache()
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
        database.DB_PATH = self.original_path
        database._INITIALIZED_DB_PATH = None
        clear_chunk_cache()
        self.temp.cleanup()

    @staticmethod
    def headers(user_id: str, *, workspace_type: str = "team", role: str = "operator",
                tenant_id: str = "tenant-team") -> dict[str, str]:
        token = access_token(
            sub=user_id,
            username=user_id,
            tenant_id=tenant_id,
            workspace_type=workspace_type,
            role=role,
            jti=f"{tenant_id}-{user_id}-{workspace_type}-{role}",
        )
        return {"Authorization": f"Bearer {token}"}

    def test_team_documents_are_shared_but_personal_and_other_tenants_are_hidden(self) -> None:
        uploaded = self.client.post(
            "/documents",
            files={"file": ("team.md", "团队客户结论：P0 优先。".encode(), "text/markdown")},
            headers=self.headers("user-a"),
        )
        self.assertEqual(uploaded.status_code, 200, uploaded.text)
        document_id = uploaded.json()["document_id"]

        member_documents = self.client.get("/documents", headers=self.headers("user-b"))
        self.assertEqual(member_documents.status_code, 200, member_documents.text)
        self.assertIn(document_id, {item["document_id"] for item in member_documents.json()})

        personal_documents = self.client.get(
            "/documents", headers=self.headers("user-b", workspace_type="personal"),
        )
        other_tenant_documents = self.client.get(
            "/documents", headers=self.headers("user-b", tenant_id="tenant-other"),
        )
        self.assertNotIn(document_id, {item["document_id"] for item in personal_documents.json()})
        self.assertNotIn(document_id, {item["document_id"] for item in other_tenant_documents.json()})

        viewer_documents = self.client.get(
            "/documents", headers=self.headers("user-c", role="viewer"),
        )
        self.assertIn(document_id, {item["document_id"] for item in viewer_documents.json()})
        denied = self.client.post(
            "/documents",
            files={"file": ("denied.md", b"denied", "text/markdown")},
            headers=self.headers("user-c", role="viewer"),
        )
        self.assertEqual(denied.status_code, 403)

    def test_team_tickets_are_shared_and_keep_creator_attribution(self) -> None:
        created = self.client.post(
            "/tickets",
            json={"title": "团队工单", "description": "由成员 A 创建", "priority": "high"},
            headers=self.headers("user-a"),
        )
        self.assertEqual(created.status_code, 200, created.text)
        ticket_id = created.json()["ticket_id"]

        shared = self.client.get(f"/tickets/{ticket_id}", headers=self.headers("user-b"))
        self.assertEqual(shared.status_code, 200, shared.text)
        self.assertEqual(shared.json()["owner_id"], "user-a")

        personal = self.client.get(
            f"/tickets/{ticket_id}", headers=self.headers("user-b", workspace_type="personal"),
        )
        outsider = self.client.get(
            f"/tickets/{ticket_id}", headers=self.headers("user-b", tenant_id="tenant-other"),
        )
        self.assertEqual(personal.status_code, 404)
        self.assertEqual(outsider.status_code, 404)

        viewer = self.client.get(
            f"/tickets/{ticket_id}", headers=self.headers("user-c", role="viewer"),
        )
        self.assertEqual(viewer.status_code, 200)
        denied = self.client.post(
            "/tickets",
            json={"title": "禁止写入", "description": "viewer", "priority": "low"},
            headers=self.headers("user-c", role="viewer"),
        )
        self.assertEqual(denied.status_code, 403)


if __name__ == "__main__":
    unittest.main()
