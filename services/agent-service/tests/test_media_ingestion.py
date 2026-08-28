import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from fastapi.testclient import TestClient

from app.citation_review import review_citations
from app.main import app
from app.models import Source
from app.retrievers import KeywordRetriever, RetrievalScope, clear_chunk_cache


SERVICE_HEADERS = {"Authorization": "Bearer integration-test-token"}


def transcript_event(
    *,
    event_id: str = "evt-1",
    tenant_id: str = "tenant-a",
    owner_id: str = "user-a",
    asset_id: str = "asset-1",
) -> dict[str, object]:
    return {
        "event_id": event_id,
        "event_type": "transcript.ready.v1",
        "occurred_at": "2026-08-29T01:02:03+08:00",
        "trace_id": f"trace-{event_id}",
        "tenant_id": tenant_id,
        "owner_id": owner_id,
        "data": {
            "asset_id": asset_id,
            "transcript_version": 1,
            "filename": f"{asset_id}.mp4",
            "language": "zh-CN",
            "duration_ms": 10_000,
            "segments": [
                {
                    "segment_id": "seg-1",
                    "sequence": 0,
                    "start_ms": 1_200,
                    "end_ms": 4_800,
                    "speaker": "客户经理",
                    "text": "客户要求预算审批必须在三个工作日内完成。",
                },
                {
                    "segment_id": "seg-2",
                    "sequence": 1,
                    "start_ms": 5_100,
                    "end_ms": 8_900,
                    "speaker": "产品经理",
                    "text": "当前流程缺少逾期提醒和负责人追踪。",
                },
            ],
        },
    }


class MediaIngestionTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.db_patcher = patch(
            "app.database.DB_PATH", Path(self.temp_dir.name) / "media-ingestion.sqlite3"
        )
        self.env_patcher = patch.dict(
            os.environ, {"MEDIA_INGEST_SERVICE_TOKEN": "integration-test-token"}
        )
        self.db_patcher.start()
        self.env_patcher.start()
        clear_chunk_cache()
        self.client = TestClient(app)

    def tearDown(self) -> None:
        clear_chunk_cache()
        self.env_patcher.stop()
        self.db_patcher.stop()
        self.temp_dir.cleanup()

    def post(self, payload: dict[str, object]):
        return self.client.post(
            "/internal/v1/media/transcripts", json=payload, headers=SERVICE_HEADERS
        )

    def test_ingests_timestamped_segments_and_deduplicates_event(self) -> None:
        first = self.post(transcript_event())
        duplicate = self.post(transcript_event())

        self.assertEqual(first.status_code, 202)
        self.assertEqual(first.json()["status"], "ingested")
        self.assertEqual(first.json()["segment_count"], 2)
        self.assertEqual(duplicate.status_code, 202)
        self.assertEqual(duplicate.json()["status"], "duplicate")
        self.assertEqual(duplicate.json()["document_id"], first.json()["document_id"])

        result = KeywordRetriever().search(
            ["预算审批"], RetrievalScope(tenant_id="tenant-a", owner_id="user-a")
        )
        hit = next(hit for hit in result.hits if hit.score > 0)
        self.assertEqual(hit.chunk.source_type, "video")
        self.assertEqual(hit.chunk.asset_id, "asset-1")
        self.assertEqual(hit.chunk.segment_id, "seg-1")
        self.assertEqual((hit.chunk.start_ms, hit.chunk.end_ms), (1_200, 4_800))
        self.assertEqual(hit.chunk.speaker, "客户经理")

    def test_different_delivery_of_same_semantic_version_is_duplicate(self) -> None:
        first = self.post(transcript_event())
        redelivery = transcript_event(event_id="evt-redelivery")
        second = self.post(redelivery)

        self.assertEqual(first.status_code, 202)
        self.assertEqual(second.status_code, 202)
        self.assertEqual(second.json()["status"], "duplicate")
        self.assertEqual(second.json()["document_id"], first.json()["document_id"])

    def test_rejects_event_id_or_semantic_version_conflicts(self) -> None:
        self.assertEqual(self.post(transcript_event()).status_code, 202)

        same_event_changed = transcript_event()
        same_event_changed["data"]["segments"][0]["text"] = "被篡改的内容"  # type: ignore[index]
        self.assertEqual(self.post(same_event_changed).status_code, 409)

        same_version_changed = transcript_event(event_id="evt-2")
        same_version_changed["data"]["segments"][0]["text"] = "另一个版本内容"  # type: ignore[index]
        self.assertEqual(self.post(same_version_changed).status_code, 409)

    def test_retrieval_scope_prevents_cross_tenant_and_cross_owner_access(self) -> None:
        self.assertEqual(self.post(transcript_event()).status_code, 202)
        self.assertEqual(
            self.post(
                transcript_event(
                    event_id="evt-b", tenant_id="tenant-b", owner_id="user-b", asset_id="asset-b"
                )
            ).status_code,
            202,
        )
        self.assertEqual(
            self.post(
                transcript_event(
                    event_id="evt-owner-b",
                    tenant_id="tenant-a",
                    owner_id="user-b",
                    asset_id="asset-owner-b",
                )
            ).status_code,
            202,
        )

        scoped = KeywordRetriever().search(
            ["预算审批"], RetrievalScope(tenant_id="tenant-a", owner_id="user-a")
        )
        assets = {hit.chunk.asset_id for hit in scoped.hits}
        self.assertEqual(assets, {"asset-1"})

        selected = KeywordRetriever().search(
            ["预算审批"],
            RetrievalScope(tenant_id="tenant-a", owner_id="user-a", asset_ids=("asset-1",)),
        )
        self.assertEqual({hit.chunk.asset_id for hit in selected.hits}, {"asset-1"})

    def test_validates_service_auth_and_segment_order(self) -> None:
        missing = self.client.post("/internal/v1/media/transcripts", json=transcript_event())
        self.assertEqual(missing.status_code, 401)

        invalid = transcript_event()
        invalid["data"]["segments"][1]["sequence"] = 4  # type: ignore[index]
        self.assertEqual(self.post(invalid).status_code, 422)

    def test_contract_files_are_valid_json_and_match_event_name(self) -> None:
        root = Path(__file__).resolve().parents[3]
        event_schema = json.loads(
            (root / "contracts/events/transcript-ready-v1.schema.json").read_text(encoding="utf-8")
        )
        evidence_schema = json.loads(
            (root / "contracts/http/evidence-source-v1.schema.json").read_text(encoding="utf-8")
        )
        self.assertEqual(event_schema["properties"]["event_type"]["const"], "transcript.ready.v1")
        self.assertEqual(evidence_schema["properties"]["source_type"]["enum"], ["document", "video"])

    def test_video_citation_is_human_playable_and_machine_addressable(self) -> None:
        source = Source(
            source_type="video",
            document_id="doc-1",
            filename="interview.mp4",
            chunk_index=0,
            score=88,
            content="客户确认三日内审批。",
            asset_id="asset-1",
            segment_id="seg-1",
            start_ms=1_200,
            end_ms=4_800,
            speaker="客户经理",
        )
        reviewed, status, _ = review_citations("审批时限已经确认。", [source])

        self.assertEqual(status, "repaired")
        self.assertIn("interview.mp4 · 00:01.200–00:04.800 · 客户经理", reviewed)
        self.assertEqual(source.model_dump()["asset_id"], "asset-1")


if __name__ == "__main__":
    unittest.main()
