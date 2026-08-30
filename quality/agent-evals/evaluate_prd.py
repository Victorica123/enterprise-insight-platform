"""Deterministic PRD golden-set gate for the six-stage analysis workflow.

This suite is intentionally independent from external LLMs and infrastructure. It
evaluates objective-ranked authorized retrieval, missing-fact decisions, explicit
conflict escalation, stage-level resume stability, and evidence-backed PRD output.
"""
from __future__ import annotations

import argparse
import json
import statistics
import sys
import tempfile
from pathlib import Path
from time import perf_counter
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[2]
API_DIR = ROOT / "services" / "agent-service"
sys.path.insert(0, str(API_DIR))

from app import database  # noqa: E402
from app.analysis_evidence import build_analysis_evidence_snapshot  # noqa: E402
from app.analysis_pipeline import resume_six_stage_analysis, run_six_stage_analysis  # noqa: E402
from app.retrievers import RetrievalScope, clear_chunk_cache  # noqa: E402


GOLDEN_PATH = Path(__file__).resolve().parent / "golden" / "prd_golden_set.jsonl"
BASELINE_PATH = Path(__file__).resolve().parent / "golden" / "baseline_prd_v1.json"
SPECIALIST_ORDER = ["business", "data", "technology", "rules"]
QUALITY_GATES = {
    "decision_accuracy": 0.90,
    "question_recall": 0.90,
    "question_precision": 0.90,
    "objective_recall1": 0.90,
    "conflict_accuracy": 1.00,
    "evidence_integrity": 1.00,
    "supported_claim_rate": 1.00,
    "acceptance_testability": 0.90,
    "checkpoint_stability": 1.00,
    "specialist_determinism": 1.00,
    "p95_latency_ms": 500.0,
}
QUALITY_METRICS = tuple(key for key in QUALITY_GATES if key != "p95_latency_ms")


def load_cases() -> list[dict[str, object]]:
    return [
        json.loads(line)
        for line in GOLDEN_PATH.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]


def run_case(case: dict[str, object]) -> dict[str, object]:
    case_id = str(case["id"])
    tenant_id = f"tenant-{case_id}"
    owner_id = "golden-owner"
    documents = list(case.get("documents", []))
    foreign_documents = list(case.get("foreign_documents", []))
    source_contents: dict[str, str] = {}

    for index, document in enumerate(documents):
        document_id = f"{case_id}-doc-{index}"
        _insert_document(document_id, tenant_id, owner_id, document)
        source_contents[document_id] = str(document["content"])
    for index, document in enumerate(foreign_documents):
        _insert_document(
            f"{case_id}-foreign-{index}", f"foreign-{tenant_id}", "foreign-owner", document,
        )

    started_at = perf_counter()
    snapshot = build_analysis_evidence_snapshot(
        str(case["objective"]), RetrievalScope(tenant_id=tenant_id, owner_id=owner_id),
    )
    initial = run_six_stage_analysis(str(case["objective"]), list(snapshot.chunks))
    initial_first_four = [stage.model_dump(mode="json") for stage in initial.stages[:4]]
    confirmations = {str(key): str(value) for key, value in dict(case["confirmations"]).items()}
    final = (
        resume_six_stage_analysis(
            str(case["objective"]), list(snapshot.chunks), initial.stages, confirmations,
        )
        if confirmations else initial
    )
    latency_ms = (perf_counter() - started_at) * 1000

    actual_questions = {question.question_id for question in final.open_questions}
    expected_questions = {str(item) for item in case["expected_questions"]}
    draft = final.prd is not None
    expected_draft = case["expected_decision"] == "draft"
    top_filename = snapshot.chunks[0].filename if snapshot.chunks else None
    expected_top = case.get("expected_top_doc")
    initial_conflict = "domain_conflict" in {
        question.question_id for question in initial.open_questions
    }

    evidence_ok = True
    supported = 0
    requirement_count = 0
    acceptance_ok = True
    video_location_ok = True
    if final.prd:
        for requirement in final.prd.requirements:
            requirement_count += 1
            evidence_ok = evidence_ok and bool(requirement.evidence)
            supporting_contents = [
                source_contents.get(evidence.document_id, "") for evidence in requirement.evidence
            ]
            is_supported = any(requirement.description in content for content in supporting_contents)
            supported += int(is_supported)
            acceptance_ok = acceptance_ok and all(
                _is_testable(criterion) for criterion in requirement.acceptance_criteria
            )
            if case.get("expect_video_location"):
                video_location_ok = video_location_ok and all(
                    evidence.source_type == "video"
                    and evidence.asset_id
                    and evidence.segment_id
                    and evidence.start_ms is not None
                    and evidence.end_ms is not None
                    for evidence in requirement.evidence
                )

    final_first_four = [stage.model_dump(mode="json") for stage in final.stages[:4]]
    result = {
        "id": case_id,
        "decision_ok": draft == expected_draft,
        "questions_ok": expected_questions.issubset(actual_questions),
        "question_precision_rate": (
            len(expected_questions & actual_questions) / len(actual_questions)
            if actual_questions else float(not expected_questions)
        ),
        "objective_ok": top_filename == expected_top,
        "conflict_ok": initial_conflict == bool(case["expect_conflict"]),
        "evidence_ok": evidence_ok and video_location_ok,
        "supported_rate": supported / requirement_count if requirement_count else 1.0,
        "acceptance_ok": acceptance_ok,
        "checkpoint_ok": not confirmations or initial_first_four == final_first_four,
        "specialists_ok": [item.key for item in initial.specialist_results] == SPECIALIST_ORDER,
        "latency_ms": latency_ms,
        "actual_questions": sorted(actual_questions),
        "top_filename": top_filename,
    }
    return result


def _insert_document(
    document_id: str,
    tenant_id: str,
    owner_id: str,
    document: dict[str, object],
) -> None:
    source_type = str(document.get("source_type") or "document")
    metadata = None
    chunk_metadata = None
    external_id = ""
    if source_type == "video":
        external_id = str(document["asset_id"])
        chunk_metadata = [{
            "asset_id": document["asset_id"],
            "segment_id": document["segment_id"],
            "start_ms": document["start_ms"],
            "end_ms": document["end_ms"],
            "speaker": document.get("speaker"),
        }]
        metadata = {"fixture": "prd-golden"}
    database.insert_document(
        document_id,
        str(document["filename"]),
        [("", str(document["content"]))],
        tenant_id=tenant_id,
        owner_id=owner_id,
        source_type=source_type,
        external_id=external_id,
        metadata=metadata,
        chunk_metadata=chunk_metadata,
    )


def _is_testable(criterion: str) -> bool:
    return bool(
        any(char.isdigit() for char in criterion)
        or any(term in criterion for term in ("以内", "不超过", "至少", "展示", "返回", "完成", "成功率"))
    )


def summarize(results: list[dict[str, object]]) -> dict[str, float | int]:
    total = len(results)
    latencies = sorted(float(item["latency_ms"]) for item in results)
    p95_index = max(0, int(len(latencies) * 0.95) - 1)
    mean = lambda key: sum(float(bool(item[key])) for item in results) / total
    return {
        "cases": total,
        "decision_accuracy": round(mean("decision_ok"), 4),
        "question_recall": round(mean("questions_ok"), 4),
        "question_precision": round(
            sum(float(item["question_precision_rate"]) for item in results) / total, 4,
        ),
        "objective_recall1": round(mean("objective_ok"), 4),
        "conflict_accuracy": round(mean("conflict_ok"), 4),
        "evidence_integrity": round(mean("evidence_ok"), 4),
        "supported_claim_rate": round(
            sum(float(item["supported_rate"]) for item in results) / total, 4,
        ),
        "acceptance_testability": round(mean("acceptance_ok"), 4),
        "checkpoint_stability": round(mean("checkpoint_ok"), 4),
        "specialist_determinism": round(mean("specialists_ok"), 4),
        "avg_latency_ms": round(statistics.mean(latencies), 2),
        "p95_latency_ms": round(latencies[p95_index], 2),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="PRD golden-set evaluation gate")
    parser.add_argument("--save-baseline", action="store_true")
    args = parser.parse_args()
    cases = load_cases()
    baseline = (
        json.loads(BASELINE_PATH.read_text(encoding="utf-8"))
        if BASELINE_PATH.exists() else None
    )

    with tempfile.TemporaryDirectory() as temp_dir:
        db_path = Path(temp_dir) / "prd-evaluation.sqlite3"
        original_initialized = database._INITIALIZED_DB_PATH
        with patch("app.database.DB_PATH", db_path):
            database._INITIALIZED_DB_PATH = None
            clear_chunk_cache()
            database.init_db()
            results = [run_case(case) for case in cases]
        database._INITIALIZED_DB_PATH = original_initialized
        clear_chunk_cache()

    summary = summarize(results)
    print("PRD V1 golden-set evaluation")
    print("-" * 88)
    for result in results:
        failed = [
            key.removesuffix("_ok")
            for key, value in result.items()
            if key.endswith("_ok") and value is False
        ]
        marker = f"  <-- {' / '.join(failed)}" if failed else ""
        print(
            f"  {result['id']}: top={result['top_filename']} "
            f"questions={result['actual_questions']}{marker}"
        )
    print("-" * 88)
    print(" ".join(
        f"{key}={value:.0%}" if isinstance(value, float) and not key.endswith("latency_ms")
        else f"{key}={value}"
        for key, value in summary.items()
    ))

    baseline_ok = True
    if baseline:
        regressions = [
            key for key in QUALITY_METRICS
            if float(summary[key]) < float(baseline[key])
        ]
        baseline_ok = not regressions
        print(f"baseline_regression={regressions or 'none'}")

    passed = all(
        float(summary[key]) >= threshold
        for key, threshold in QUALITY_GATES.items()
        if key != "p95_latency_ms"
    ) and float(summary["p95_latency_ms"]) <= QUALITY_GATES["p95_latency_ms"] and baseline_ok
    print(f"quality_gate={'passed' if passed else 'failed'}")

    if args.save_baseline:
        BASELINE_PATH.write_text(
            json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8",
        )
        print(f"baseline saved to {BASELINE_PATH.name}")
    return 0 if passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
