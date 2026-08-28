"""Deterministic V5 release gate: token accounting, chat logs, replay, and feedback loop."""
from pathlib import Path
import os
import statistics
import sys
import tempfile
from time import perf_counter
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "apps" / "api"))

# 离线门禁：关闭 LLM 路由（确定性 + 不消耗 API 额度），走规则降级通道
os.environ.setdefault("LLM_ROUTER_ENABLED", "0")

from fastapi.testclient import TestClient  # noqa: E402

from app.main import app  # noqa: E402
from app.rag import ingest_document  # noqa: E402


FIXTURE_TEXT = (
    "客户 B 的项目原计划在 2026 年 6 月 20 日交付。\n"
    "有人操作失误导致了项目交付时间推迟到 2026 年 7 月 8 日。\n"
    "延期原因：操作失误。\n"
    "项目负责人是李四。\n"
    "合同中约定，如果延期超过 18 天，需要向客户提交说明书。"
)

QUESTIONS = [
    ("客户B的项目为什么延期？", "answered"),
    ("项目负责人是谁？", "answered"),
    ("项目为什么延期，同时合同有什么风险？", "answered"),
    ("火星基地的氧气供应方案是什么？", "refused"),
]

REQUIRED_SUMMARY_KEYS = [
    "total_tokens",
    "avg_tokens_per_request",
    "total_estimated_cost_usd",
    "avg_cost_per_request_usd",
    "tokens_by_answer_mode",
    "cost_by_answer_mode",
    "feedback_count",
    "satisfaction_rate",
]

QUALITY_GATES = {
    "observability_checks": 1.0,
    "p95_chat_latency_ms": 300.0,
}


def main() -> int:
    with tempfile.TemporaryDirectory() as temp_dir:
        db_path = Path(temp_dir) / "v5-evaluation.sqlite3"
        with patch("app.database.DB_PATH", db_path):
            client = TestClient(app)
            ingest_document("sample.md", FIXTURE_TEXT)

            latencies: list[float] = []
            responses = []
            for question, _ in QUESTIONS:
                started = perf_counter()
                response = client.post(
                    "/chat",
                    json={
                        "question": question,
                        "answer_mode": "local",
                        "retriever_mode": "keyword",
                        "workflow_mode": "agentic",
                    },
                )
                latencies.append((perf_counter() - started) * 1000)
                responses.append(response.json())

            outcomes_ok = all(
                (payload["agent_summary"]["evidence_status"] == "passed") == (expected == "answered")
                for payload, (_, expected) in zip(responses, QUESTIONS)
            )
            log_ids_ok = all(payload["log_id"] > 0 for payload in responses)
            answered_tokens_ok = all(
                payload["token_usage"] is not None and payload["token_usage"]["total_tokens"] > 0
                for payload, (_, expected) in zip(responses, QUESTIONS)
                if expected == "answered"
            )

            logs = client.get("/chat-logs", headers={"X-User-Role": "operator"}).json()
            logs_recorded = len(logs) == len(QUESTIONS)

            refused_logs = client.get("/chat-logs", params={"outcome": "refused"}, headers={"X-User-Role": "operator"}).json()
            refused_id = refused_logs[0]["log_id"] if refused_logs else 0
            replay = client.get(f"/chat-logs/{refused_id}", headers={"X-User-Role": "operator"}).json() if refused_id else {}
            replay_ok = bool(refused_logs) and bool(replay.get("trace"))

            up = client.post(f"/chat-logs/{responses[0]['log_id']}/feedback", json={"rating": "up"})
            down = client.post(
                f"/chat-logs/{responses[1]['log_id']}/feedback",
                json={"rating": "down", "note": "评测反馈样例"},
            )
            summary = client.get("/metrics/summary").json()
            feedback_ok = (
                up.status_code == 200
                and down.status_code == 200
                and summary["feedback_count"] == 2
                and summary["satisfaction_rate"] == 0.5
            )
            summary_keys_ok = all(key in summary for key in REQUIRED_SUMMARY_KEYS)
            token_accounting_ok = summary["total_tokens"] > 0 and summary["total_estimated_cost_usd"] == 0.0

    checks = {
        "answer_refusal_decisions": outcomes_ok,
        "log_ids_returned": log_ids_ok,
        "answered_requests_have_tokens": answered_tokens_ok,
        "all_requests_logged": logs_recorded,
        "failure_replay_with_trace": replay_ok,
        "feedback_loop_reflected": feedback_ok,
        "summary_token_cost_fields": summary_keys_ok,
        "local_mode_zero_cost": token_accounting_ok,
    }
    observability_score = sum(checks.values()) / len(checks)
    p95_latency_ms = sorted(latencies)[max(0, int(len(latencies) * 0.95) - 1)]

    print("V5 observability evaluation")
    print("-" * 72)
    for name, passed in checks.items():
        print(f"{name}={'passed' if passed else 'failed'}")
    print("-" * 72)
    print(f"observability_checks={observability_score:.0%}")
    print(f"total_tokens={summary['total_tokens']}")
    print(f"avg_tokens_per_request={summary['avg_tokens_per_request']}")
    print(f"avg_chat_latency_ms={statistics.mean(latencies):.2f}")
    print(f"p95_chat_latency_ms={p95_latency_ms:.2f}")

    passed = (
        observability_score >= QUALITY_GATES["observability_checks"]
        and p95_latency_ms <= QUALITY_GATES["p95_chat_latency_ms"]
    )
    print(f"quality_gate={'passed' if passed else 'failed'}")
    print("thresholds=observability=100%, p95<=300ms")
    return 0 if passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
