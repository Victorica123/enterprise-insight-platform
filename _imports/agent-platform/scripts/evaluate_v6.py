"""Deterministic V6 golden-set gate: retrieval recall, answer fidelity, refusal accuracy.

A1 方法论核心：不是"规则系统检查规则系统"，而是用人工标注的黄金问答集
（scripts/golden/golden_set.jsonl + fixtures/ 语料）做端到端裁判：

- decision_accuracy：该答的答了、该拒的拒了（evidence 门控行为）
- recall@3：期望文档是否出现在 Top-3 来源里（检索命中）
- fact_coverage：答案是否包含标注的关键事实（回答保真）

用法：
    python scripts/evaluate_v6.py                  # 跑门禁，与基线对比
    python scripts/evaluate_v6.py --save-baseline  # 首次运行，把当前数字存为基线

判定用"事实子串 + 期望文档"而非 chunk 索引，对 A4 重切块免疫。
"""
from __future__ import annotations

import argparse
import json
import os
import statistics
import sys
import tempfile
from pathlib import Path
from time import perf_counter
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]
API_DIR = ROOT / "apps" / "api"
sys.path.insert(0, str(API_DIR))

# 离线门禁：关闭 LLM 路由（确定性 + 不消耗 API 额度），走规则降级通道
os.environ.setdefault("LLM_ROUTER_ENABLED", "0")

from app.agentic_rag import answer_agentic_question  # noqa: E402
from app.embeddings import warm_up_embeddings  # noqa: E402
from app.rag import ingest_document  # noqa: E402


GOLDEN_DIR = Path(__file__).resolve().parent / "golden"
FIXTURES_DIR = GOLDEN_DIR / "fixtures"
GOLDEN_SET_PATH = GOLDEN_DIR / "golden_set.jsonl"
BASELINE_PATH = GOLDEN_DIR / "baseline_v6.json"

MODES = ["keyword", "embedding", "hybrid"]

# 回归门槛：与基线一起维护。升级步骤（A2/A3/A4）只允许提升不允许跌破。
QUALITY_GATES = {
    "decision_accuracy": 0.90,
    "hybrid_recall3": 0.75,
    "hybrid_fact_coverage": 0.70,
    "p95_latency_ms": 500.0,
}


def load_golden_cases() -> list[dict[str, object]]:
    cases: list[dict[str, object]] = []
    for line in GOLDEN_SET_PATH.read_text(encoding="utf-8").splitlines():
        if line.strip():
            cases.append(json.loads(line))
    return cases


def load_fixture_files() -> list[tuple[str, str]]:
    files: list[tuple[str, str]] = []
    for path in sorted(FIXTURES_DIR.glob("*.md")):
        files.append((path.name, path.read_text(encoding="utf-8")))
    return files


def ingest_fixtures() -> None:
    for filename, content in load_fixture_files():
        ingest_document(filename, content)


def judge_case(case: dict[str, object], response) -> dict[str, object]:
    summary = response.agent_summary
    answered = bool(summary and summary.evidence_status == "passed")
    should_answer = bool(case["should_answer"])

    expected_docs = [str(item) for item in case["expected_docs"]]
    source_filenames = [source.filename for source in response.sources]

    retrieval_ok: bool | None = None
    fact_ok: bool | None = None
    if should_answer:
        retrieval_ok = bool(set(expected_docs) & set(source_filenames))
        expected_facts = [str(item).lower() for item in case["expected_facts"]]
        answer_lower = response.answer.lower()
        fact_ok = answered and any(fact in answer_lower for fact in expected_facts)

    return {
        "id": case["id"],
        "decision_ok": answered == should_answer,
        "retrieval_ok": retrieval_ok,
        "fact_ok": fact_ok,
        "answered": answered,
        "evidence_status": summary.evidence_status if summary else "",
        "source_filenames": source_filenames,
    }


def run_mode(cases: list[dict[str, object]], mode: str) -> dict[str, object]:
    results: list[dict[str, object]] = []
    latencies: list[float] = []
    warm_up_embeddings()  # 模型加载延迟不计入请求 P95
    for case in cases:
        started_at = perf_counter()
        response = answer_agentic_question(str(case["question"]), "local", mode)
        latencies.append((perf_counter() - started_at) * 1000)
        results.append(judge_case(case, response))

    total = len(results)
    answered_cases = [r for r, c in zip(results, cases) if c["should_answer"]]
    decision_ok = sum(bool(r["decision_ok"]) for r in results) / total
    retrieval_ok = (
        sum(bool(r["retrieval_ok"]) for r in answered_cases) / len(answered_cases)
        if answered_cases
        else 1.0
    )
    fact_ok = (
        sum(bool(r["fact_ok"]) for r in answered_cases) / len(answered_cases)
        if answered_cases
        else 1.0
    )
    sorted_latencies = sorted(latencies)
    p95 = sorted_latencies[max(0, int(len(sorted_latencies) * 0.95) - 1)]

    return {
        "mode": mode,
        "results": results,
        "decision_accuracy": round(decision_ok, 4),
        "recall3": round(retrieval_ok, 4),
        "fact_coverage": round(fact_ok, 4),
        "avg_latency_ms": round(statistics.mean(latencies), 2),
        "p95_latency_ms": round(p95, 2),
    }


def print_mode_summary(summary: dict[str, object], baseline: dict[str, object] | None) -> None:
    mode = summary["mode"]
    print(f"\n[{mode}]")
    for result in summary["results"]:
        marks = []
        if result["decision_ok"] is False:
            marks.append("decision_wrong")
        if result["retrieval_ok"] is False:
            marks.append("doc_miss")
        if result["fact_ok"] is False:
            marks.append("fact_miss")
        flag = f"  <-- {' / '.join(marks)}" if marks else ""
        print(f"  {result['id']}: {'answered' if result['answered'] else 'refused'}{flag}")

    print(
        f"  decision={summary['decision_accuracy']:.0%} "
        f"recall3={summary['recall3']:.0%} "
        f"fact={summary['fact_coverage']:.0%} "
        f"p95={summary['p95_latency_ms']:.1f}ms"
    )
    if baseline:
        delta = lambda cur, base: f"{cur - base:+.1%}"
        print(
            f"    vs baseline: decision {delta(summary['decision_accuracy'], baseline['decision_accuracy'])}"
            f" recall3 {delta(summary['recall3'], baseline['recall3'])}"
            f" fact {delta(summary['fact_coverage'], baseline['fact_coverage'])}"
        )


def main() -> int:
    parser = argparse.ArgumentParser(description="V6 golden-set evaluation gate")
    parser.add_argument("--save-baseline", action="store_true", help="save current numbers as baseline")
    args = parser.parse_args()

    cases = load_golden_cases()
    baseline: dict[str, object] | None = None
    if BASELINE_PATH.exists():
        baseline = json.loads(BASELINE_PATH.read_text(encoding="utf-8"))

    summaries: dict[str, dict[str, object]] = {}
    with tempfile.TemporaryDirectory() as temp_dir:
        db_path = Path(temp_dir) / "v6-evaluation.sqlite3"
        with patch("app.database.DB_PATH", db_path):
            ingest_fixtures()
            for mode in MODES:
                summaries[mode] = run_mode(cases, mode)

    print("V6 golden-set evaluation")
    print("-" * 88)
    for mode in MODES:
        print_mode_summary(summaries[mode], baseline.get(mode) if baseline else None)

    hybrid = summaries["hybrid"]
    print("-" * 88)
    gates_passed = (
        summaries["keyword"]["decision_accuracy"] >= QUALITY_GATES["decision_accuracy"]
        and hybrid["recall3"] >= QUALITY_GATES["hybrid_recall3"]
        and hybrid["fact_coverage"] >= QUALITY_GATES["hybrid_fact_coverage"]
        and hybrid["p95_latency_ms"] <= QUALITY_GATES["p95_latency_ms"]
    )
    print(f"quality_gate={'passed' if gates_passed else 'failed'}")
    print(
        "thresholds="
        f"decision>={QUALITY_GATES['decision_accuracy']:.0%}, "
        f"hybrid_recall3>={QUALITY_GATES['hybrid_recall3']:.0%}, "
        f"hybrid_fact>={QUALITY_GATES['hybrid_fact_coverage']:.0%}, "
        f"p95<={QUALITY_GATES['p95_latency_ms']:.0f}ms"
    )

    if args.save_baseline:
        BASELINE_PATH.write_text(
            json.dumps(
                {
                    mode: {
                        "decision_accuracy": summaries[mode]["decision_accuracy"],
                        "recall3": summaries[mode]["recall3"],
                        "fact_coverage": summaries[mode]["fact_coverage"],
                        "avg_latency_ms": summaries[mode]["avg_latency_ms"],
                        "p95_latency_ms": summaries[mode]["p95_latency_ms"],
                    }
                    for mode in MODES
                },
                ensure_ascii=False,
                indent=2,
            ),
            encoding="utf-8",
        )
        print(f"baseline saved to {BASELINE_PATH.name}")

    return 0 if gates_passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
