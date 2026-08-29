import tempfile
import unittest
from pathlib import Path

from fastapi.testclient import TestClient

from app import database
from app.analysis_pipeline import run_six_stage_analysis
from app.main import app
from app.retrievers import Chunk, clear_chunk_cache


class SixStagePipelineTests(unittest.TestCase):
    def test_waits_for_material_gaps_then_resumes_to_evidence_backed_prd(self) -> None:
        chunks = [Chunk(
            document_id="doc-1", filename="interview.mp4", chunk_index=0,
            content="客户希望简化审批流程。", source_type="video", asset_id="asset-1",
            segment_id="seg-1", start_ms=1200, end_ms=4800,
        )]

        waiting = run_six_stage_analysis("生成审批流程 PRD", chunks)

        self.assertIsNone(waiting.prd)
        self.assertEqual(waiting.stages[-1].status, "WAITING_CONFIRMATION")
        question_ids = {question.question_id for question in waiting.open_questions}
        self.assertIn("decision_maker", question_ids)
        self.assertIn("acceptance_criteria", question_ids)

        resumed = run_six_stage_analysis("生成审批流程 PRD", chunks, {
            "decision_maker": "产品负责人",
            "acceptance_criteria": "审批提交后 2 秒内展示结果",
            "priority_rule": "合规阻塞项优先",
        })

        self.assertEqual(resumed.open_questions, [])
        self.assertIsNotNone(resumed.prd)
        requirement = resumed.prd.requirements[0]
        self.assertEqual(requirement.evidence[0].asset_id, "asset-1")
        self.assertEqual(requirement.evidence[0].start_ms, 1200)
        self.assertEqual(requirement.acceptance_criteria, ["审批提交后 2 秒内展示结果"])


class AnalysisApiTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.original_path = database.DB_PATH
        database.DB_PATH = Path(self.temp.name) / "analysis.sqlite3"
        database._INITIALIZED_DB_PATH = None
        clear_chunk_cache()
        database.init_db()
        database.insert_document(
            "doc-video", "review.mp4", [("", "产品负责人要求 P0 优先交付。验收标准是 2 秒内完成。存在合规风险。")],
            tenant_id="tenant-a", owner_id="user-a", source_type="video", external_id="asset-a",
            chunk_metadata=[{
                "asset_id": "asset-a", "segment_id": "segment-0",
                "start_ms": 0, "end_ms": 5000, "speaker": "产品负责人",
            }],
        )
        self.client = TestClient(app)

    def tearDown(self) -> None:
        database.DB_PATH = self.original_path
        database._INITIALIZED_DB_PATH = None
        clear_chunk_cache()
        self.temp.cleanup()

    def test_creates_draft_and_enforces_tenant_owner_lookup(self) -> None:
        headers = {"X-User-Role": "operator", "X-User-Id": "user-a", "X-Tenant-Id": "tenant-a"}
        created = self.client.post(
            "/analysis/sessions", headers=headers,
            json={"objective": "生成合规交付 PRD", "asset_ids": ["asset-a"]},
        )

        self.assertEqual(created.status_code, 201, created.text)
        payload = created.json()
        self.assertEqual(payload["status"], "DRAFT_READY")
        self.assertEqual(len(payload["stages"]), 6)
        self.assertEqual(payload["prd"]["requirements"][0]["evidence"][0]["asset_id"], "asset-a")

        hidden = self.client.get(
            f"/analysis/sessions/{payload['session_id']}",
            headers={**headers, "X-Tenant-Id": "tenant-b"},
        )
        self.assertEqual(hidden.status_code, 404)

    def test_personal_owner_uses_two_explicit_steps_and_receives_audit_chain(self) -> None:
        headers = {
            "X-User-Role": "admin", "X-User-Id": "user-a",
            "X-Tenant-Id": "tenant-a", "X-Workspace-Type": "personal",
        }
        created = self.client.post(
            "/analysis/sessions", headers=headers,
            json={"objective": "发布合规交付 PRD", "asset_ids": ["asset-a"]},
        ).json()

        requested_response = self.client.post(
            f"/analysis/sessions/{created['session_id']}/publication/request", headers=headers,
        )
        self.assertEqual(requested_response.status_code, 200, requested_response.text)
        requested = requested_response.json()
        self.assertEqual(requested["status"], "PUBLISH_PENDING")
        self.assertEqual(requested["publication"]["policy"], "OWNER_RECONFIRMATION")
        self.assertEqual(requested["prd"]["publication_status"], "PUBLISH_PENDING")

        approved_response = self.client.post(
            f"/analysis/sessions/{created['session_id']}/publication/approve", headers=headers,
            json={
                "request_id": requested["publication"]["request_id"],
                "approval_token": requested["publication"]["approval_token"],
                "confirmation": "PUBLISH",
            },
        )
        self.assertEqual(approved_response.status_code, 200, approved_response.text)
        approved = approved_response.json()
        self.assertEqual(approved["status"], "PUBLISHED")
        self.assertEqual(approved["publication"]["approved_by"], "user-a")
        self.assertIsNone(approved["publication"]["approval_token"])
        self.assertEqual(approved["prd"]["publication_status"], "PUBLISHED")

        audit = self.client.get(
            f"/analysis/sessions/{created['session_id']}/audit", headers=headers,
        )
        self.assertEqual(audit.status_code, 200, audit.text)
        self.assertEqual(
            [event["action"] for event in audit.json()],
            ["PUBLICATION_REQUESTED", "PUBLICATION_APPROVED"],
        )

    def test_team_publication_rejects_self_approval_and_accepts_second_member(self) -> None:
        author = {
            "X-User-Role": "operator", "X-User-Id": "user-a",
            "X-Tenant-Id": "tenant-a", "X-Workspace-Type": "team",
        }
        reviewer = {
            "X-User-Role": "operator", "X-User-Id": "user-b",
            "X-Tenant-Id": "tenant-a", "X-Workspace-Type": "team",
        }
        created = self.client.post(
            "/analysis/sessions", headers=author,
            json={"objective": "团队发布合规 PRD", "asset_ids": ["asset-a"]},
        ).json()
        requested = self.client.post(
            f"/analysis/sessions/{created['session_id']}/publication/request", headers=author,
        ).json()
        approval = {
            "request_id": requested["publication"]["request_id"],
            "approval_token": requested["publication"]["approval_token"],
            "confirmation": "PUBLISH",
        }

        self_approval = self.client.post(
            f"/analysis/sessions/{created['session_id']}/publication/approve",
            headers=author, json=approval,
        )
        self.assertEqual(self_approval.status_code, 403)

        cross_tenant = self.client.post(
            f"/analysis/sessions/{created['session_id']}/publication/approve",
            headers={**reviewer, "X-Tenant-Id": "tenant-b"}, json=approval,
        )
        self.assertEqual(cross_tenant.status_code, 404)

        queue = self.client.get("/analysis/publication-queue", headers=reviewer)
        self.assertEqual(queue.status_code, 200, queue.text)
        self.assertEqual([item["session_id"] for item in queue.json()], [created["session_id"]])

        approved = self.client.post(
            f"/analysis/sessions/{created['session_id']}/publication/approve",
            headers=reviewer, json=approval,
        )
        self.assertEqual(approved.status_code, 200, approved.text)
        self.assertEqual(approved.json()["publication"]["approved_by"], "user-b")


if __name__ == "__main__":
    unittest.main()
