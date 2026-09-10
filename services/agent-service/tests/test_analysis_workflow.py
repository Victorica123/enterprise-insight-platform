import tempfile
import unittest
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime
from pathlib import Path
from unittest.mock import patch

from app import analysis_pipeline, database
from app.analysis_pipeline import resume_six_stage_analysis, run_six_stage_analysis
from app.main import app
from app.publication_artifacts import decide_knowledge_candidate, get_publication_deliverables
from app.rag import answer_question
from app.retrievers import Chunk, RetrievalScope, clear_chunk_cache, load_chunks
from fastapi.testclient import TestClient


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

    def test_domain_specialists_merge_deterministically_and_surface_conflicts(self) -> None:
        chunks = [Chunk(
            document_id="doc-1", filename="meeting.md", chunk_index=0,
            content=(
                "产品负责人要求 P0 上线审批 API，验收标准为 2 秒内完成。"
                "但材料存在两种口径冲突：业务要求保存全部数据，合规则禁止保存隐私字段。"
            ),
        )]

        run = run_six_stage_analysis("生成审批 PRD", chunks)

        self.assertEqual(
            [result.key for result in run.specialist_results],
            ["business", "data", "technology", "rules"],
        )
        self.assertIn("domain_conflict", {item.question_id for item in run.open_questions})
        self.assertTrue(any(item.startswith("[冲突]") for item in run.stages[2].findings))

    def test_one_specialist_failure_is_isolated_and_requires_review(self) -> None:
        original = analysis_pipeline._run_one_specialist

        def fail_data(config, chunks):
            if config.key == "data":
                raise RuntimeError("simulated")
            return original(config, chunks)

        with patch("app.analysis_pipeline._run_one_specialist", side_effect=fail_data):
            run = run_six_stage_analysis("生成 PRD", [Chunk(
                document_id="doc-1", filename="meeting.md", chunk_index=0,
                content="产品负责人要求 P0 上线，验收标准为 2 秒内完成。",
            )])

        self.assertEqual(len(run.specialist_results), 4)
        self.assertEqual(run.specialist_results[1].error, "RuntimeError")
        self.assertIn("specialist_review", {item.question_id for item in run.open_questions})

    def test_resume_preserves_completed_business_checkpoint(self) -> None:
        original_chunks = [Chunk(
            document_id="doc-old", filename="old.md", chunk_index=0,
            content="客户希望简化流程。",
        )]
        waiting = run_six_stage_analysis("生成流程 PRD", original_chunks)
        frozen = [stage.model_dump(mode="json") for stage in waiting.stages[:4]]

        resumed = resume_six_stage_analysis(
            "生成流程 PRD",
            original_chunks,
            waiting.stages,
            {
                "decision_maker": "产品负责人",
                "acceptance_criteria": "2 秒内完成",
                "priority_rule": "P0 优先",
            },
        )

        self.assertEqual(
            [stage.model_dump(mode="json") for stage in resumed.stages[:4]], frozen,
        )
        self.assertIsNotNone(resumed.prd)

    def test_text_confirmation_cannot_replace_a_missing_evidence_snapshot(self) -> None:
        waiting = run_six_stage_analysis("生成权益 PRD", [])

        resumed = resume_six_stage_analysis(
            "生成权益 PRD",
            [],
            waiting.stages,
            {
                "evidence_scope": "使用某个未绑定的文档",
                "decision_maker": "产品负责人",
                "acceptance_criteria": "2 秒内完成",
                "priority_rule": "P0 优先",
            },
        )

        self.assertIsNone(resumed.prd)
        self.assertEqual(
            [question.question_id for question in resumed.open_questions], ["evidence_scope"],
        )


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

    def _publish_personal_candidate(self) -> tuple[dict[str, str], dict, dict]:
        headers = {
            "X-User-Role": "admin", "X-User-Id": "user-a",
            "X-Tenant-Id": "tenant-a", "X-Workspace-Type": "personal",
        }
        created = self.client.post(
            "/analysis/sessions", headers=headers,
            json={"objective": "治理知识生命周期 PRD", "asset_ids": ["asset-a"]},
        ).json()
        requested = self.client.post(
            f"/analysis/sessions/{created['session_id']}/publication/request", headers=headers,
        ).json()
        published = self.client.post(
            f"/analysis/sessions/{created['session_id']}/publication/approve", headers=headers,
            json={
                "request_id": requested["publication"]["request_id"],
                "approval_token": requested["publication"]["approval_token"],
                "confirmation": "PUBLISH",
            },
        )
        self.assertEqual(published.status_code, 200, published.text)
        deliverables = self.client.get(
            f"/analysis/sessions/{created['session_id']}/deliverables", headers=headers,
        ).json()
        candidate = deliverables["knowledge_candidates"][0]
        decided = self.client.post(
            f"/analysis/sessions/{created['session_id']}/knowledge-candidates/{candidate['candidate_id']}/decision",
            headers=headers, json={"approved": True},
        )
        self.assertEqual(decided.status_code, 200, decided.text)
        return headers, created, decided.json()

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
        self.assertEqual(payload["checkpoint_version"], 1)
        self.assertEqual(payload["retrieval_mode"], "hybrid")
        self.assertEqual(len(payload["evidence_snapshot_sha256"]), 64)
        self.assertEqual(payload["prd"]["requirements"][0]["evidence"][0]["asset_id"], "asset-a")

        hidden = self.client.get(
            f"/analysis/sessions/{payload['session_id']}",
            headers={**headers, "X-Tenant-Id": "tenant-b"},
        )
        self.assertEqual(hidden.status_code, 404)

    def test_snapshot_is_objective_ranked_after_authorization_filtering(self) -> None:
        database.insert_document(
            "doc-refund", "refund.md",
            [("", "退款产品负责人要求 P0 优先，验收标准是退款申请 2 秒内受理。")],
            tenant_id="tenant-a", owner_id="user-a",
        )
        database.insert_document(
            "doc-hiring", "hiring.md",
            [("", "招聘负责人要求 P0 优先，验收标准是三天内完成简历筛选。")],
            tenant_id="tenant-a", owner_id="user-a",
        )
        database.insert_document(
            "doc-other-tenant", "refund-secret.md",
            [("", "退款产品负责人要求 P0 优先，验收标准是退款申请 1 秒内受理。")],
            tenant_id="tenant-b", owner_id="user-b",
        )
        headers = {"X-User-Role": "operator", "X-User-Id": "user-a", "X-Tenant-Id": "tenant-a"}

        response = self.client.post(
            "/analysis/sessions", headers=headers,
            json={"objective": "生成退款受理 PRD", "asset_ids": []},
        )

        self.assertEqual(response.status_code, 201, response.text)
        payload = response.json()
        self.assertEqual(
            payload["prd"]["requirements"][0]["evidence"][0]["document_id"],
            "doc-refund",
        )
        all_ids = {
            evidence["document_id"]
            for stage in payload["stages"]
            for evidence in stage["evidence"]
        }
        self.assertNotIn("doc-other-tenant", all_ids)

    def test_objective_ranked_snapshot_stays_frozen_across_resume(self) -> None:
        database.insert_document(
            "doc-checkpoint", "checkout-review.mp4", [("", "客户希望优化结算体验。")],
            tenant_id="tenant-a", owner_id="user-a", source_type="video",
            external_id="asset-checkpoint",
            chunk_metadata=[{
                "asset_id": "asset-checkpoint", "segment_id": "segment-checkpoint",
                "start_ms": 1000, "end_ms": 4000, "speaker": "客户",
            }],
        )
        headers = {"X-User-Role": "operator", "X-User-Id": "user-a", "X-Tenant-Id": "tenant-a"}
        created_response = self.client.post(
            "/analysis/sessions", headers=headers,
            json={"objective": "生成结算体验 PRD", "asset_ids": ["asset-checkpoint"]},
        )
        self.assertEqual(created_response.status_code, 201, created_response.text)
        created = created_response.json()
        self.assertEqual(created["status"], "WAITING_CONFIRMATION")
        first_four = created["stages"][:4]

        database.insert_document(
            "doc-late", "late.mp4", [("", "产品负责人要求 P0，验收标准 1 秒；这是稍后写入的新事实。")],
            tenant_id="tenant-a", owner_id="user-a", source_type="video",
            external_id="asset-checkpoint", source_version=2,
            chunk_metadata=[{
                "asset_id": "asset-checkpoint", "segment_id": "segment-late",
                "start_ms": 5000, "end_ms": 9000, "speaker": "产品负责人",
            }],
        )
        answers = {
            question["question_id"]: {
                "decision_maker": "产品负责人",
                "acceptance_criteria": "提交后 2 秒内完成",
                "priority_rule": "P0 优先",
                "domain_conflict": "以合规要求为准",
                "specialist_review": "产品负责人复核",
                "evidence_scope": "使用冻结视频证据",
            }[question["question_id"]]
            for question in created["open_questions"]
        }
        resumed_response = self.client.post(
            f"/analysis/sessions/{created['session_id']}/confirm", headers=headers,
            json={"resume_token": created["resume_token"], "answers": answers},
        )

        self.assertEqual(resumed_response.status_code, 200, resumed_response.text)
        resumed = resumed_response.json()
        self.assertEqual(resumed["status"], "DRAFT_READY")
        self.assertEqual(resumed["checkpoint_version"], 2)
        self.assertEqual(resumed["evidence_revision"], created["evidence_revision"])
        self.assertEqual(resumed["evidence_snapshot_sha256"], created["evidence_snapshot_sha256"])
        self.assertEqual(resumed["stages"][:4], first_four)
        evidence_ids = {
            evidence["document_id"]
            for requirement in resumed["prd"]["requirements"]
            for evidence in requirement["evidence"]
        }
        self.assertEqual(evidence_ids, {"doc-checkpoint"})

    def test_resume_token_is_consumed_once_with_database_cas(self) -> None:
        database.insert_document(
            "doc-cas", "cas.mp4", [("", "客户希望优化退款流程。")],
            tenant_id="tenant-a", owner_id="user-a", source_type="video", external_id="asset-cas",
            chunk_metadata=[{
                "asset_id": "asset-cas", "segment_id": "segment-cas",
                "start_ms": 0, "end_ms": 3000, "speaker": "客户",
            }],
        )
        headers = {"X-User-Role": "operator", "X-User-Id": "user-a", "X-Tenant-Id": "tenant-a"}
        created = self.client.post(
            "/analysis/sessions", headers=headers,
            json={"objective": "生成退款 PRD", "asset_ids": ["asset-cas"]},
        ).json()
        answer_values = {
            "decision_maker": "产品负责人",
            "acceptance_criteria": "退款申请 2 秒内受理",
            "priority_rule": "P0 优先",
            "domain_conflict": "以合规口径为准",
            "specialist_review": "产品负责人复核",
            "evidence_scope": "使用冻结证据",
        }
        payload = {
            "resume_token": created["resume_token"],
            "answers": {
                item["question_id"]: answer_values[item["question_id"]]
                for item in created["open_questions"]
            },
        }

        def confirm_once() -> int:
            with TestClient(app) as client:
                return client.post(
                    f"/analysis/sessions/{created['session_id']}/confirm",
                    headers=headers, json=payload,
                ).status_code

        with ThreadPoolExecutor(max_workers=2) as executor:
            statuses = sorted(executor.map(lambda _: confirm_once(), range(2)))

        self.assertEqual(statuses, [200, 409])
        stored = self.client.get(
            f"/analysis/sessions/{created['session_id']}", headers=headers,
        ).json()
        self.assertEqual(stored["checkpoint_version"], 2)
        self.assertEqual(stored["status"], "DRAFT_READY")

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

        deliverables_response = self.client.get(
            f"/analysis/sessions/{created['session_id']}/deliverables", headers=headers,
        )
        self.assertEqual(deliverables_response.status_code, 200, deliverables_response.text)
        deliverables = deliverables_response.json()
        self.assertEqual(deliverables["version"]["version_number"], 1)
        self.assertEqual(len(deliverables["version"]["content_sha256"]), 64)
        self.assertEqual(deliverables["knowledge_candidates"][0]["status"], "PENDING")
        self.assertEqual(deliverables["action_items"][0]["status"], "DRAFT")

        candidate = deliverables["knowledge_candidates"][0]
        decided = self.client.post(
            f"/analysis/sessions/{created['session_id']}/knowledge-candidates/{candidate['candidate_id']}/decision",
            headers=headers, json={"approved": True},
        )
        self.assertEqual(decided.status_code, 200, decided.text)
        decided_candidate = decided.json()
        self.assertEqual(decided_candidate["status"], "APPROVED")
        self.assertTrue(decided_candidate["knowledge_document_id"].startswith("knowledge-"))
        self.assertEqual(len(decided_candidate["knowledge_content_sha256"]), 64)
        self.assertIsNotNone(decided_candidate["knowledge_published_at"])

        documents = self.client.get("/documents", headers=headers).json()
        managed = [item for item in documents if item["managed"]]
        self.assertEqual([item["document_id"] for item in managed], [decided_candidate["knowledge_document_id"]])
        self.assertEqual(managed[0]["source_type"], "knowledge")
        protected = self.client.delete(
            f"/documents/{decided_candidate['knowledge_document_id']}", headers=headers,
        )
        self.assertEqual(protected.status_code, 404)

        clear_chunk_cache()
        answer = answer_question(
            "已批准业务知识",
            answer_mode="local",
            retriever_mode="keyword",
            scope=RetrievalScope(tenant_id="tenant-a", owner_id="user-a"),
        )
        approved_source = next(
            source for source in answer.sources if source.origin_type == "approved_knowledge"
        )
        self.assertEqual(approved_source.knowledge_candidate_id, candidate["candidate_id"])
        self.assertEqual(approved_source.prd_version_id, candidate["version_id"])
        self.assertEqual(approved_source.content_sha256, decided_candidate["knowledge_content_sha256"])

        action = deliverables["action_items"][0]
        drafted = self.client.post(
            f"/analysis/sessions/{created['session_id']}/action-items/{action['action_item_id']}/ticket-draft",
            headers=headers,
        )
        self.assertEqual(drafted.status_code, 200, drafted.text)
        self.assertEqual(drafted.json()["action_item"]["status"], "TICKET_PENDING_APPROVAL")
        pending_id = drafted.json()["pending_action_id"]
        approved_ticket = self.client.post(
            f"/pending-actions/{pending_id}/approve",
            headers=headers, json={"approved": True},
        )
        self.assertEqual(approved_ticket.status_code, 200, approved_ticket.text)
        self.assertEqual(approved_ticket.json()["status"], "succeeded")
        completed = self.client.get(
            f"/analysis/sessions/{created['session_id']}/deliverables", headers=headers,
        ).json()["action_items"][0]
        self.assertEqual(completed["status"], "TICKET_CREATED")
        self.assertEqual(
            completed["ticket_id"], approved_ticket.json()["result"]["ticket"]["ticket_id"],
        )
        repeated = self.client.post(
            f"/analysis/sessions/{created['session_id']}/action-items/{action['action_item_id']}/ticket-draft",
            headers=headers,
        )
        self.assertEqual(repeated.status_code, 200, repeated.text)
        self.assertEqual(repeated.json()["pending_action_id"], pending_id)
        self.assertEqual(repeated.json()["action_item"]["status"], "TICKET_CREATED")

    def test_knowledge_materialization_rolls_back_when_indexing_fails(self) -> None:
        headers = {
            "X-User-Role": "admin", "X-User-Id": "user-a",
            "X-Tenant-Id": "tenant-a", "X-Workspace-Type": "personal",
        }
        created = self.client.post(
            "/analysis/sessions", headers=headers,
            json={"objective": "验证知识沉淀事务", "asset_ids": ["asset-a"]},
        ).json()
        requested = self.client.post(
            f"/analysis/sessions/{created['session_id']}/publication/request", headers=headers,
        ).json()
        self.client.post(
            f"/analysis/sessions/{created['session_id']}/publication/approve", headers=headers,
            json={
                "request_id": requested["publication"]["request_id"],
                "approval_token": requested["publication"]["approval_token"],
                "confirmation": "PUBLISH",
            },
        )
        candidate_id = get_publication_deliverables(
            created["session_id"], "tenant-a",
        ).knowledge_candidates[0].candidate_id

        with patch("app.publication_artifacts.index_document_graph", side_effect=RuntimeError("index failed")):
            with self.assertRaisesRegex(RuntimeError, "index failed"):
                decide_knowledge_candidate(
                    candidate_id,
                    tenant_id="tenant-a",
                    actor_id="user-a",
                    approved=True,
                    decided_at=datetime.now(UTC),
                )

        candidate = get_publication_deliverables(
            created["session_id"], "tenant-a",
        ).knowledge_candidates[0]
        self.assertEqual(candidate.status, "PENDING")
        self.assertIsNone(candidate.knowledge_document_id)
        with database.connect() as conn:
            count = conn.execute(
                "select count(*) as c from documents where source_type = 'knowledge'"
            ).fetchone()["c"]
        self.assertEqual(count, 0)

    def test_personal_supersede_and_revoke_preserve_lineage_and_historical_citations(self) -> None:
        headers, created, candidate = self._publish_personal_candidate()
        session_id = created["session_id"]
        candidate_id = candidate["candidate_id"]
        self.assertEqual(candidate["knowledge_status"], "ACTIVE")
        self.assertEqual(candidate["knowledge_version_number"], 1)

        historical = self.client.post(
            "/chat", headers=headers,
            json={
                "question": "已批准业务知识",
                "answer_mode": "local", "retriever_mode": "keyword",
                "workflow_mode": "standard",
            },
        ).json()
        original_source = next(
            source for source in historical["sources"]
            if source.get("knowledge_candidate_id") == candidate_id
        )
        self.assertEqual(original_source["knowledge_lifecycle_status"], "ACTIVE")
        original_document_id = original_source["document_id"]
        original_revision = database.get_content_revision()

        lifecycle_path = (
            f"/analysis/sessions/{session_id}/knowledge-candidates/{candidate_id}/lifecycle-requests"
        )
        requested = self.client.post(
            lifecycle_path,
            headers=headers,
            json={
                "action": "SUPERSEDE",
                "reason": "验收口径已由业务负责人修订",
                "replacement_statement": "替代版本唯一标记：审批结果必须在 1 秒内展示。",
                "replacement_evidence": candidate["evidence"],
            },
        )
        self.assertEqual(requested.status_code, 201, requested.text)
        lifecycle = requested.json()
        pending_bundle = self.client.get(
            f"/analysis/sessions/{session_id}/deliverables", headers=headers,
        ).json()
        self.assertEqual(
            pending_bundle["knowledge_candidates"][0]["pending_lifecycle_request_id"],
            lifecycle["request_id"],
        )

        approved = self.client.post(
            f"{lifecycle_path}/{lifecycle['request_id']}/decision",
            headers=headers, json={"approved": True},
        )
        self.assertEqual(approved.status_code, 200, approved.text)
        self.assertEqual(approved.json()["status"], "APPROVED")
        repeated = self.client.post(
            f"{lifecycle_path}/{lifecycle['request_id']}/decision",
            headers=headers, json={"approved": True},
        )
        self.assertEqual(repeated.status_code, 409)

        superseded_bundle = self.client.get(
            f"/analysis/sessions/{session_id}/deliverables", headers=headers,
        ).json()
        versions = superseded_bundle["knowledge_versions"]
        self.assertEqual([item["status"] for item in versions], ["SUPERSEDED", "ACTIVE"])
        self.assertEqual(versions[1]["predecessor_version_id"], versions[0]["knowledge_version_id"])
        self.assertEqual(versions[0]["successor_version_id"], versions[1]["knowledge_version_id"])
        current_candidate = superseded_bundle["knowledge_candidates"][0]
        self.assertEqual(current_candidate["knowledge_version_number"], 2)
        self.assertGreater(database.get_content_revision(), original_revision)
        clear_chunk_cache()
        authorized_chunks = load_chunks(RetrievalScope(tenant_id="tenant-a", owner_id="user-a"))
        self.assertNotIn(original_document_id, {chunk.document_id for chunk in authorized_chunks})
        self.assertIn(
            current_candidate["knowledge_document_id"],
            {chunk.document_id for chunk in authorized_chunks},
        )

        replay = self.client.get(
            f"/chat-logs/{historical['log_id']}", headers=headers,
        )
        self.assertEqual(replay.status_code, 200, replay.text)
        replay_source = next(
            source for source in replay.json()["sources"]
            if source.get("knowledge_candidate_id") == candidate_id
        )
        self.assertEqual(replay_source["document_id"], original_document_id)
        self.assertEqual(replay_source["knowledge_lifecycle_status"], "SUPERSEDED")
        self.assertEqual(
            replay_source["superseded_by_document_id"],
            current_candidate["knowledge_document_id"],
        )

        current_history = self.client.post(
            "/chat", headers=headers,
            json={
                "question": "替代版本唯一标记",
                "answer_mode": "local", "retriever_mode": "keyword",
                "workflow_mode": "standard",
            },
        ).json()
        self.assertTrue(any(
            source.get("knowledge_version_number") == 2
            for source in current_history["sources"]
        ))
        revoke = self.client.post(
            lifecycle_path,
            headers=headers,
            json={"action": "REVOKE", "reason": "业务负责人确认该规则不再适用"},
        )
        self.assertEqual(revoke.status_code, 201, revoke.text)
        def decide_revoke() -> int:
            with TestClient(app) as client:
                return client.post(
                    f"{lifecycle_path}/{revoke.json()['request_id']}/decision",
                    headers=headers, json={"approved": True},
                ).status_code

        with ThreadPoolExecutor(max_workers=2) as executor:
            revoke_statuses = sorted(executor.map(lambda _: decide_revoke(), range(2)))
        self.assertEqual(revoke_statuses, [200, 409])
        final_bundle = self.client.get(
            f"/analysis/sessions/{session_id}/deliverables", headers=headers,
        ).json()
        self.assertEqual(final_bundle["knowledge_candidates"][0]["knowledge_status"], "REVOKED")
        self.assertIsNone(final_bundle["knowledge_candidates"][0]["active_knowledge_version_id"])
        self.assertEqual(
            [item["status"] for item in final_bundle["knowledge_versions"]],
            ["SUPERSEDED", "REVOKED"],
        )
        clear_chunk_cache()
        self.assertNotIn(
            candidate_id,
            {chunk.knowledge_candidate_id for chunk in load_chunks(
                RetrievalScope(tenant_id="tenant-a", owner_id="user-a"),
            )},
        )
        current_replay = self.client.get(
            f"/chat-logs/{current_history['log_id']}", headers=headers,
        ).json()
        current_replay_source = next(
            source for source in current_replay["sources"]
            if source.get("knowledge_candidate_id") == candidate_id
        )
        self.assertEqual(current_replay_source["knowledge_lifecycle_status"], "REVOKED")
        with database.connect() as conn:
            retained = conn.execute(
                "select count(*) as c from documents where external_id = ? and source_type = 'knowledge'",
                (candidate_id,),
            ).fetchone()["c"]
            graph_refs = conn.execute(
                "select count(*) as c from graph_relations where document_id in (?, ?)",
                (versions[0]["document_id"], versions[1]["document_id"]),
            ).fetchone()["c"]
        self.assertEqual(retained, 2)
        self.assertEqual(graph_refs, 0)

    def test_lifecycle_transaction_rolls_back_when_graph_rebuild_fails(self) -> None:
        headers, created, candidate = self._publish_personal_candidate()
        lifecycle_path = (
            f"/analysis/sessions/{created['session_id']}/knowledge-candidates/"
            f"{candidate['candidate_id']}/lifecycle-requests"
        )
        requested = self.client.post(
            lifecycle_path, headers=headers,
            json={
                "action": "SUPERSEDE", "reason": "测试原子回滚",
                "replacement_statement": "替代版本用于验证事务回滚。",
                "replacement_evidence": candidate["evidence"],
            },
        ).json()

        with patch(
            "app.publication_artifacts.rebuild_graph_scope",
            side_effect=RuntimeError("graph rebuild failed"),
        ):
            with self.assertRaisesRegex(RuntimeError, "graph rebuild failed"):
                self.client.post(
                    f"{lifecycle_path}/{requested['request_id']}/decision",
                    headers=headers, json={"approved": True},
                )

        bundle = get_publication_deliverables(created["session_id"], "tenant-a")
        self.assertIsNotNone(bundle)
        assert bundle is not None
        self.assertEqual([item.status for item in bundle.knowledge_versions], ["ACTIVE"])
        self.assertEqual(bundle.knowledge_lifecycle_requests[-1].status, "PENDING")
        self.assertEqual(bundle.knowledge_candidates[0].knowledge_version_number, 1)
        rejected = self.client.post(
            f"{lifecycle_path}/{requested['request_id']}/decision",
            headers=headers, json={"approved": False},
        )
        self.assertEqual(rejected.status_code, 200, rejected.text)
        self.assertEqual(rejected.json()["status"], "REJECTED")
        after_rejection = get_publication_deliverables(created["session_id"], "tenant-a")
        assert after_rejection is not None
        self.assertEqual(after_rejection.knowledge_candidates[0].knowledge_status, "ACTIVE")
        self.assertIsNone(after_rejection.knowledge_candidates[0].pending_lifecycle_request_id)
        retry = self.client.post(
            lifecycle_path, headers=headers,
            json={"action": "REVOKE", "reason": "拒绝后允许重新发起治理"},
        )
        self.assertEqual(retry.status_code, 201, retry.text)

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

        # Team sessions are tenant-shared, while the same user in personal mode
        # cannot use the team tenant as an owner-bypass.
        shared = self.client.get(
            f"/analysis/sessions/{created['session_id']}", headers=reviewer,
        )
        self.assertEqual(shared.status_code, 200, shared.text)
        personal_reviewer = {**reviewer, "X-Workspace-Type": "personal"}
        hidden = self.client.get(
            f"/analysis/sessions/{created['session_id']}", headers=personal_reviewer,
        )
        self.assertEqual(hidden.status_code, 404)
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

        deliverables = self.client.get(
            f"/analysis/sessions/{created['session_id']}/deliverables", headers=author,
        ).json()
        candidate_id = deliverables["knowledge_candidates"][0]["candidate_id"]
        self_decision = self.client.post(
            f"/analysis/sessions/{created['session_id']}/knowledge-candidates/{candidate_id}/decision",
            headers=author, json={"approved": True},
        )
        self.assertEqual(self_decision.status_code, 403)
        reviewed = self.client.post(
            f"/analysis/sessions/{created['session_id']}/knowledge-candidates/{candidate_id}/decision",
            headers=reviewer, json={"approved": True},
        )
        self.assertEqual(reviewed.status_code, 200, reviewed.text)
        self.assertEqual(reviewed.json()["decided_by"], "user-b")

        lifecycle_path = (
            f"/analysis/sessions/{created['session_id']}/knowledge-candidates/"
            f"{candidate_id}/lifecycle-requests"
        )
        lifecycle = self.client.post(
            lifecycle_path,
            headers=author,
            json={
                "action": "SUPERSEDE", "reason": "团队验收口径修订",
                "replacement_statement": "团队知识替代版本：审批结果 1 秒内展示。",
                "replacement_evidence": reviewed.json()["evidence"],
            },
        )
        self.assertEqual(lifecycle.status_code, 201, lifecycle.text)
        self_review = self.client.post(
            f"{lifecycle_path}/{lifecycle.json()['request_id']}/decision",
            headers=author, json={"approved": True},
        )
        self.assertEqual(self_review.status_code, 403)
        cross_tenant_review = self.client.post(
            f"{lifecycle_path}/{lifecycle.json()['request_id']}/decision",
            headers={**reviewer, "X-Tenant-Id": "tenant-b"}, json={"approved": True},
        )
        self.assertEqual(cross_tenant_review.status_code, 404)
        second_review = self.client.post(
            f"{lifecycle_path}/{lifecycle.json()['request_id']}/decision",
            headers=reviewer, json={"approved": True},
        )
        self.assertEqual(second_review.status_code, 200, second_review.text)
        lineage = self.client.get(
            f"/analysis/sessions/{created['session_id']}/deliverables", headers=reviewer,
        ).json()["knowledge_versions"]
        self.assertEqual([item["status"] for item in lineage], ["SUPERSEDED", "ACTIVE"])


if __name__ == "__main__":
    unittest.main()
