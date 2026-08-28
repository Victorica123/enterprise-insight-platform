"""Small deterministic V3 release gate for the controlled tool workflow."""
from pathlib import Path
import sys
import tempfile
from time import perf_counter
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "apps" / "api"))

from app.ticket_store import get_pending_action, get_tool_metrics_summary, list_tickets  # noqa: E402
from app.tools import execute_tool, resolve_tool_action  # noqa: E402


PAYLOAD = {
    "title": "V3 评测工单",
    "description": "验证审批前不写入、审批后恰好执行一次。",
    "priority": "high",
}

QUALITY_GATES = {
    "safety_checks": 1.0,
    "exact_once_violations": 0,
    "p95_latency_ms": 200.0,
}


def main() -> int:
    with tempfile.TemporaryDirectory() as temp_dir:
        db_path = Path(temp_dir) / "v3-evaluation.sqlite3"
        with patch("app.database.DB_PATH", db_path):
            started = perf_counter()
            draft = execute_tool("create_ticket", PAYLOAD, actor_role="operator")
            no_write_before_approval = len(list_tickets()) == 0
            approved = resolve_tool_action(draft.pending_action_id, True, actor_role="operator")
            one_write_after_approval = len(list_tickets()) == 1
            duplicate = resolve_tool_action(draft.pending_action_id, True, actor_role="operator")
            duplicate_did_not_write = len(list_tickets()) == 1 and duplicate.already_resolved

            rejected_draft = execute_tool(
                "create_ticket", {**PAYLOAD, "title": "拒绝草稿"}, actor_role="operator"
            )
            rejected = resolve_tool_action(rejected_draft.pending_action_id, False, actor_role="operator")
            rejection_did_not_write = rejected.status == "rejected" and len(list_tickets()) == 1

            expired_draft = execute_tool(
                "create_ticket",
                {**PAYLOAD, "title": "过期草稿"},
                actor_role="operator",
                approval_ttl_seconds=-1,
            )
            expired = resolve_tool_action(expired_draft.pending_action_id, True, actor_role="operator")
            expiry_blocked_write = expired.status == "expired" and len(list_tickets()) == 1

            invalid = execute_tool(
                "create_ticket", {**PAYLOAD, "priority": "invalid"}, actor_role="operator"
            )
            denied = execute_tool("create_ticket", PAYLOAD, actor_role="viewer")
            validation_blocked = not invalid.success and invalid.status == "failed"
            permission_blocked = not denied.success and denied.status == "denied"
            action = get_pending_action(draft.pending_action_id)
            metrics = get_tool_metrics_summary()
            total_latency_ms = (perf_counter() - started) * 1000

    checks = {
        "draft_without_write": no_write_before_approval,
        "approved_once": approved.status == "succeeded" and one_write_after_approval,
        "duplicate_safe": duplicate_did_not_write and action.execution_count == 1,
        "rejection_safe": rejection_did_not_write,
        "expiry_safe": expiry_blocked_write,
        "validation_safe": validation_blocked,
        "permission_safe": permission_blocked,
    }
    safety_score = sum(checks.values()) / len(checks)
    p95_latency_ms = float(metrics["p95_duration_ms"])

    print("V3 controlled-tool evaluation")
    print("-" * 72)
    for name, passed in checks.items():
        print(f"{name}={'passed' if passed else 'failed'}")
    print("-" * 72)
    print(f"safety_checks={safety_score:.0%}")
    print(f"exact_once_violations={metrics['exact_once_violations']}")
    print(f"tool_success_rate={metrics['success_rate']:.0%}")
    print(f"tool_p95_duration_ms={metrics['p95_duration_ms']:.2f}")
    print(f"evaluation_total_latency_ms={total_latency_ms:.2f}")

    passed = (
        safety_score >= QUALITY_GATES["safety_checks"]
        and metrics["exact_once_violations"] <= QUALITY_GATES["exact_once_violations"]
        and p95_latency_ms <= QUALITY_GATES["p95_latency_ms"]
    )
    print(f"quality_gate={'passed' if passed else 'failed'}")
    print("thresholds=safety=100%, exact_once_violations=0, p95<=200ms")
    return 0 if passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
