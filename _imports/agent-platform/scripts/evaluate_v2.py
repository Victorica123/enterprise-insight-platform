from dataclasses import dataclass
from pathlib import Path
import os
import statistics
import sys
import tempfile
from time import perf_counter
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]
API_DIR = ROOT / "apps" / "api"
sys.path.insert(0, str(API_DIR))

# 离线门禁：关闭 LLM 路由（确定性 + 不消耗 API 额度），走规则降级通道
os.environ.setdefault("LLM_ROUTER_ENABLED", "0")

from app.agentic_rag import answer_agentic_question  # noqa: E402
from app.document_parser import parse_document  # noqa: E402
from app.embeddings import warm_up_embeddings  # noqa: E402
from app.rag import ingest_document  # noqa: E402


@dataclass(frozen=True)
class EvalCase:
    question: str
    expected_intent: str
    should_answer: bool
    expected_rounds: int


CASES = [
    EvalCase("甲方客户A的项目为什么延期？", "causal", True, 1),
    EvalCase("项目为什么延期，同时合同有什么风险？", "risk", True, 1),
    EvalCase("项目负责人是谁？", "fact", True, 1),
    EvalCase("火星基地的氧气供应方案是什么？", "general", False, 2),
]

QUALITY_GATES = {
    "intent_accuracy": 0.90,
    "answer_refusal_accuracy": 0.90,
    "retrieval_round_accuracy": 0.90,
    "citation_coverage": 1.00,
    # 墙钟门禁：含本地 ONNX embedding 推理。实测本机 p95 在 83~125ms 随负载波动，
    # 100ms 阈值在开发机/CI 共享 runner 上会误报。调到 200ms 仍能捕获
    # 算法级回退（N+1 检索、重复嵌入等会把延迟推高一个数量级）。
    "p95_latency_ms": 200.0,
}


def main() -> int:
    # 自包含门禁：临时库 + 自带语料（与 v3~v6 一致），不依赖开发库状态。
    # 旧版直读开发库，全新克隆里库为空会让"该回答"用例全部误判为拒答。
    with tempfile.TemporaryDirectory() as temp_dir:
        with patch("app.database.DB_PATH", Path(temp_dir) / "v2-evaluation.sqlite3"):
            corpus = ROOT / "docs" / "sample-project-delay-cn.pdf"
            ingest_document(corpus.name, parse_document(filename=corpus.name, raw=corpus.read_bytes()))
            return _run_cases()


def _run_cases() -> int:
    warm_up_embeddings()  # 模型加载延迟不计入请求 P95（生产上启动时预热）
    results: list[dict[str, object]] = []
    for case in CASES:
        started_at = perf_counter()
        response = answer_agentic_question(case.question, "local", "hybrid")
        latency_ms = (perf_counter() - started_at) * 1000
        summary = response.agent_summary
        answered = summary.evidence_status == "passed"
        citation_ready = summary.citation_status in {"passed", "repaired"} and "[来源 1]" in response.answer
        results.append(
            {
                "case": case,
                "intent_ok": summary.intent == case.expected_intent,
                "decision_ok": answered == case.should_answer,
                "rounds_ok": summary.retrieval_rounds == case.expected_rounds,
                "citation_ok": citation_ready if case.should_answer else True,
                "latency_ms": latency_ms,
                "actual_intent": summary.intent,
                "actual_status": summary.evidence_status,
                "actual_rounds": summary.retrieval_rounds,
            }
        )

    print("V2 offline evaluation")
    print("-" * 88)
    for result in results:
        case = result["case"]
        print(
            f"{case.question} | intent={result['actual_intent']} | "
            f"status={result['actual_status']} | rounds={result['actual_rounds']} | "
            f"latency={result['latency_ms']:.2f}ms"
        )

    total = len(results)
    intent_accuracy = sum(bool(item["intent_ok"]) for item in results) / total
    decision_accuracy = sum(bool(item["decision_ok"]) for item in results) / total
    round_accuracy = sum(bool(item["rounds_ok"]) for item in results) / total
    citation_coverage = sum(bool(item["citation_ok"]) for item in results) / total
    latencies = [float(item["latency_ms"]) for item in results]
    average_rounds = statistics.mean(int(item["actual_rounds"]) for item in results)

    print("-" * 88)
    print(f"intent_accuracy={intent_accuracy:.0%}")
    print(f"answer_refusal_accuracy={decision_accuracy:.0%}")
    print(f"retrieval_round_accuracy={round_accuracy:.0%}")
    print(f"citation_coverage={citation_coverage:.0%}")
    print(f"avg_retrieval_rounds={average_rounds:.2f}")
    print(f"avg_latency_ms={statistics.mean(latencies):.2f}")
    p95_latency_ms = sorted(latencies)[-1]
    print(f"p95_latency_ms={p95_latency_ms:.2f}")

    cases_passed = all(
        bool(item["intent_ok"] and item["decision_ok"] and item["rounds_ok"] and item["citation_ok"])
        for item in results
    )
    gates_passed = (
        intent_accuracy >= QUALITY_GATES["intent_accuracy"]
        and decision_accuracy >= QUALITY_GATES["answer_refusal_accuracy"]
        and round_accuracy >= QUALITY_GATES["retrieval_round_accuracy"]
        and citation_coverage >= QUALITY_GATES["citation_coverage"]
        and p95_latency_ms <= QUALITY_GATES["p95_latency_ms"]
    )
    print(f"quality_gate={'passed' if cases_passed and gates_passed else 'failed'}")
    print(
        "thresholds="
        f"intent>={QUALITY_GATES['intent_accuracy']:.0%}, "
        f"decision>={QUALITY_GATES['answer_refusal_accuracy']:.0%}, "
        f"rounds>={QUALITY_GATES['retrieval_round_accuracy']:.0%}, "
        f"citation={QUALITY_GATES['citation_coverage']:.0%}, "
        f"p95<={QUALITY_GATES['p95_latency_ms']:.0f}ms"
    )
    return 0 if cases_passed and gates_passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
