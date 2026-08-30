"""Deterministic golden gate for governed approved-knowledge evolution."""
from __future__ import annotations

import json
import statistics
import sys
import tempfile
from pathlib import Path
from time import perf_counter

from fastapi.testclient import TestClient


ROOT = Path(__file__).resolve().parents[2]
API_DIR = ROOT / "services" / "agent-service"
sys.path.insert(0, str(API_DIR))

from app import database  # noqa: E402
from app.main import app  # noqa: E402
from app.retrievers import RetrievalScope, clear_chunk_cache, load_chunks  # noqa: E402


GOLDEN_PATH = Path(__file__).resolve().parent / "golden" / "knowledge_lifecycle_golden_set.jsonl"
QUALITY_GATES = {
    "decision_accuracy": 1.0,
    "future_retrieval_accuracy": 1.0,
    "lineage_integrity": 1.0,
    "historical_status_accuracy": 1.0,
    "tenant_isolation": 1.0,
    "four_eyes_enforcement": 1.0,
    "idempotency_conflict": 1.0,
    "graph_invalidation": 1.0,
    "physical_retention": 1.0,
    "p95_latency_ms": 3000.0,
}


def load_cases() -> list[dict[str, object]]:
    return [
        json.loads(line)
        for line in GOLDEN_PATH.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]


def headers(user_id: str, workspace_type: str, *, tenant_id: str = "tenant-golden") -> dict[str, str]:
    return {
        "X-User-Role": "admin" if workspace_type == "personal" else "operator",
        "X-User-Id": user_id,
        "X-Tenant-Id": tenant_id,
        "X-Workspace-Type": workspace_type,
    }


def run_case(case: dict[str, object]) -> dict[str, object]:
    workspace_type = str(case["workspace_type"])
    author = headers("author", workspace_type)
    reviewer = headers("reviewer", workspace_type)
    client = TestClient(app)
    database.insert_document(
        "golden-source", "golden-review.mp4",
        [("", "产品负责人要求 P0 优先，审批结果 2 秒内展示，并保留合规审计。")],
        tenant_id="tenant-golden", owner_id="author", source_type="video",
        external_id="asset-golden",
        chunk_metadata=[{
            "asset_id": "asset-golden", "segment_id": "segment-golden",
            "start_ms": 0, "end_ms": 4000, "speaker": "产品负责人",
        }],
    )
    started_at = perf_counter()
    created = client.post(
        "/analysis/sessions", headers=author,
        json={"objective": "生成知识治理验收 PRD", "asset_ids": ["asset-golden"]},
    ).json()
    if created["status"] == "WAITING_CONFIRMATION":
        answer_values = {
            "decision_maker": "产品负责人",
            "acceptance_criteria": "审批结果 2 秒内展示",
            "priority_rule": "P0 合规事项优先",
            "domain_conflict": "以合规要求为准",
            "specialist_review": "由产品负责人复核",
            "evidence_scope": "使用冻结的视频证据",
        }
        created = client.post(
            f"/analysis/sessions/{created['session_id']}/confirm", headers=author,
            json={
                "resume_token": created["resume_token"],
                "answers": {
                    item["question_id"]: answer_values[item["question_id"]]
                    for item in created["open_questions"]
                },
            },
        ).json()
    requested = client.post(
        f"/analysis/sessions/{created['session_id']}/publication/request", headers=author,
    ).json()
    publication_reviewer = reviewer if workspace_type == "team" else author
    published = client.post(
        f"/analysis/sessions/{created['session_id']}/publication/approve",
        headers=publication_reviewer,
        json={
            "request_id": requested["publication"]["request_id"],
            "approval_token": requested["publication"]["approval_token"],
            "confirmation": "PUBLISH",
        },
    )
    bundle = client.get(
        f"/analysis/sessions/{created['session_id']}/deliverables", headers=author,
    ).json()
    candidate = bundle["knowledge_candidates"][0]
    candidate_reviewer = reviewer if workspace_type == "team" else author
    approved_candidate = client.post(
        f"/analysis/sessions/{created['session_id']}/knowledge-candidates/{candidate['candidate_id']}/decision",
        headers=candidate_reviewer, json={"approved": True},
    )
    history = client.post(
        "/chat", headers=author,
        json={
            "question": "已批准业务知识", "answer_mode": "local",
            "retriever_mode": "keyword", "workflow_mode": "standard",
        },
    ).json()
    original_source = next(
        source for source in history["sources"]
        if source.get("knowledge_candidate_id") == candidate["candidate_id"]
    )
    original_document_id = original_source["document_id"]
    action = str(case["action"])
    lifecycle_path = (
        f"/analysis/sessions/{created['session_id']}/knowledge-candidates/"
        f"{candidate['candidate_id']}/lifecycle-requests"
    )
    lifecycle_payload: dict[str, object] = {
        "action": action,
        "reason": f"golden {action.lower()} governance decision",
    }
    if action == "SUPERSEDE":
        lifecycle_payload.update({
            "replacement_statement": "黄金集替代知识：审批结果必须在 1 秒内展示。",
            "replacement_evidence": candidate["evidence"],
        })
    lifecycle = client.post(
        lifecycle_path, headers=author, json=lifecycle_payload,
    ).json()
    self_decision_status = (
        client.post(
            f"{lifecycle_path}/{lifecycle['request_id']}/decision",
            headers=author, json={"approved": True},
        ).status_code
        if workspace_type == "team" else 200
    )
    decision_actor = reviewer if workspace_type == "team" else author
    decision = client.post(
        f"{lifecycle_path}/{lifecycle['request_id']}/decision",
        headers=decision_actor, json={"approved": True},
    )
    repeated = client.post(
        f"{lifecycle_path}/{lifecycle['request_id']}/decision",
        headers=decision_actor, json={"approved": True},
    )
    final_bundle = client.get(
        f"/analysis/sessions/{created['session_id']}/deliverables", headers=author,
    ).json()
    versions = final_bundle["knowledge_versions"]
    final_candidate = final_bundle["knowledge_candidates"][0]
    clear_chunk_cache()
    active_knowledge = [
        chunk for chunk in load_chunks(RetrievalScope(
            tenant_id="tenant-golden", owner_id=None if workspace_type == "team" else "author",
        ))
        if chunk.knowledge_candidate_id == candidate["candidate_id"]
    ]
    replay = client.get(f"/chat-logs/{history['log_id']}", headers=author).json()
    replay_source = next(
        source for source in replay["sources"]
        if source.get("knowledge_candidate_id") == candidate["candidate_id"]
    )
    cross_tenant = client.get(
        f"/analysis/sessions/{created['session_id']}/deliverables",
        headers=headers("intruder", workspace_type, tenant_id="tenant-foreign"),
    )
    with database.connect() as conn:
        retained = conn.execute(
            "select count(*) as c from documents where source_type = 'knowledge' and external_id = ?",
            (candidate["candidate_id"],),
        ).fetchone()["c"]
        stale_graph = conn.execute(
            "select count(*) as c from graph_relations where document_id = ?",
            (original_document_id,),
        ).fetchone()["c"]
    expected_active = case["expected_active_version"]
    expected_statuses = list(case["expected_versions"])
    lineage_ok = [item["status"] for item in versions] == expected_statuses
    if action == "SUPERSEDE":
        lineage_ok = lineage_ok and (
            versions[0]["successor_version_id"] == versions[1]["knowledge_version_id"]
            and versions[1]["predecessor_version_id"] == versions[0]["knowledge_version_id"]
        )
    result = {
        "id": case["id"],
        "decision_ok": published.status_code == 200 and approved_candidate.status_code == 200 and decision.status_code == 200,
        "retrieval_ok": (
            len(active_knowledge) == (1 if expected_active else 0)
            and all(chunk.knowledge_version_number == expected_active for chunk in active_knowledge)
        ),
        "lineage_ok": lineage_ok and final_candidate["knowledge_version_number"] == len(versions),
        "history_ok": replay_source["knowledge_lifecycle_status"] == case["expected_history_status"],
        "isolation_ok": cross_tenant.status_code == 404,
        "four_eyes_ok": workspace_type != "team" or self_decision_status == 403,
        "idempotency_ok": repeated.status_code == 409,
        "graph_ok": stale_graph == 0,
        "retention_ok": retained == len(versions),
        "latency_ms": (perf_counter() - started_at) * 1000,
    }
    client.close()
    return result


def summarize(results: list[dict[str, object]]) -> dict[str, float | int]:
    latencies = sorted(float(item["latency_ms"]) for item in results)
    p95_index = max(0, int(len(latencies) * 0.95) - 1)
    metric_keys = {
        "decision_accuracy": "decision_ok",
        "future_retrieval_accuracy": "retrieval_ok",
        "lineage_integrity": "lineage_ok",
        "historical_status_accuracy": "history_ok",
        "tenant_isolation": "isolation_ok",
        "four_eyes_enforcement": "four_eyes_ok",
        "idempotency_conflict": "idempotency_ok",
        "graph_invalidation": "graph_ok",
        "physical_retention": "retention_ok",
    }
    summary: dict[str, float | int] = {"cases": len(results)}
    for metric, key in metric_keys.items():
        summary[metric] = round(sum(bool(item[key]) for item in results) / len(results), 4)
    summary["avg_latency_ms"] = round(statistics.mean(latencies), 2)
    summary["p95_latency_ms"] = round(latencies[p95_index], 2)
    return summary


def main() -> int:
    results: list[dict[str, object]] = []
    original_path = database.DB_PATH
    original_initialized = database._INITIALIZED_DB_PATH
    try:
        for case in load_cases():
            with tempfile.TemporaryDirectory() as temp_dir:
                database.DB_PATH = Path(temp_dir) / "knowledge-lifecycle.sqlite3"
                database._INITIALIZED_DB_PATH = None
                clear_chunk_cache()
                database.init_db()
                results.append(run_case(case))
    finally:
        database.DB_PATH = original_path
        database._INITIALIZED_DB_PATH = original_initialized
        clear_chunk_cache()
    summary = summarize(results)
    print("Knowledge lifecycle V1 golden-set evaluation")
    print("-" * 88)
    for result in results:
        failed = [key for key, value in result.items() if key.endswith("_ok") and not value]
        print(f"{result['id']}: {'PASS' if not failed else 'FAIL ' + ','.join(failed)} ({result['latency_ms']:.2f}ms)")
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    failures = []
    for metric, threshold in QUALITY_GATES.items():
        actual = float(summary[metric])
        if metric == "p95_latency_ms":
            if actual > threshold:
                failures.append(f"{metric}={actual} > {threshold}")
        elif actual < threshold:
            failures.append(f"{metric}={actual} < {threshold}")
    if failures:
        print("Gate failed: " + "; ".join(failures), file=sys.stderr)
        return 1
    print("Gate passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
