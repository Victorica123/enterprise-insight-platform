"""Deterministic V4 release gate: graph extraction quality + Graph Agent integration."""
from pathlib import Path
import statistics
import sys
import tempfile
from time import perf_counter
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "apps" / "api"))

from app.agentic_rag import answer_agentic_question  # noqa: E402
from app.graph_rag import lookup_graph  # noqa: E402
from app.graph_store import find_paths, get_graph_overview, list_relations, rebuild_graph  # noqa: E402
from app.rag import ingest_document  # noqa: E402
from app.ticket_store import create_ticket  # noqa: E402


FIXTURE_TEXT = (
    "客户 B 的项目原计划在 2026 年 6 月 20 日交付。\n"
    "有人操作失误导致了项目交付时间推迟到 2026 年 7 月 8 日。\n"
    "延期原因：操作失误。\n"
    "项目负责人是李四。\n"
    "合同中约定，如果延期超过 18 天，需要向客户提交说明书。"
)

EXPECTED_ENTITIES = {
    ("customer", "客户B"),
    ("project", "客户B项目"),
    ("person", "李四"),
    ("cause", "操作失误"),
    ("date", "2026-06-20"),
    ("date", "2026-07-08"),
}

EXPECTED_RELATIONS = {
    ("客户B", "委托", "客户B项目"),
    ("客户B项目", "负责人", "李四"),
    ("客户B项目", "延期原因", "操作失误"),
    ("客户B项目", "原计划交付", "2026-06-20"),
    ("客户B项目", "调整后交付", "2026-07-08"),
}

QUALITY_GATES = {
    "entity_recall": 0.90,
    "relation_recall": 0.90,
    "structural_checks": 1.0,
    # 墙钟门禁含 SQLite 打开+BFS，本机实测 ~45ms 临界；CI 共享 runner 更慢，留足余量防误报
    "p95_graph_latency_ms": 150.0,
}


def main() -> int:
    with tempfile.TemporaryDirectory() as temp_dir:
        db_path = Path(temp_dir) / "v4-evaluation.sqlite3"
        with patch("app.database.DB_PATH", db_path):
            ingest_document("sample.md", FIXTURE_TEXT)
            create_ticket("客户B项目延期跟进", "跟进客户B项目的延期恢复计划", status="open")
            rebuild_graph()

            overview = get_graph_overview()
            relations = list_relations()
            entity_pairs = set()
            from app.graph_store import list_entities

            for entity in list_entities(limit=500):
                entity_pairs.add((entity.entity_type, entity.name))
            triples = {(r.source_name, r.relation_type, r.target_name) for r in relations}

            entity_recall = len(EXPECTED_ENTITIES & entity_pairs) / len(EXPECTED_ENTITIES)
            relation_recall = len(EXPECTED_RELATIONS & triples) / len(EXPECTED_RELATIONS)

            paths = find_paths("客户B", "李四", max_depth=3)
            path_found = bool(paths)

            lookup = lookup_graph("客户B的项目为什么延期？", "causal")
            risk_chain_found = bool(lookup.risk_chains)

            ticket_linked = any(
                r.source_type == "ticket" and r.target_name in {"客户B", "客户B项目"}
                for r in relations
            )

            response = answer_agentic_question("客户B的项目为什么延期？", "local", "keyword")
            summary = response.agent_summary
            agent_used = "Graph Agent" in summary.agents
            paths_in_summary = len(summary.graph_paths) >= 3
            context_in_answer = "【关系图谱】" in response.answer

            latencies = []
            for _ in range(20):
                started = perf_counter()
                lookup_graph("客户B的项目为什么延期？", "causal")
                latencies.append((perf_counter() - started) * 1000)

    checks = {
        "path_customer_to_owner": path_found,
        "risk_chain_built": risk_chain_found,
        "ticket_linked_into_graph": ticket_linked,
        "graph_agent_in_workflow": agent_used,
        "graph_paths_in_summary": paths_in_summary,
        "graph_context_in_answer": context_in_answer,
    }
    structural_score = sum(checks.values()) / len(checks)
    p95_latency_ms = sorted(latencies)[max(0, int(len(latencies) * 0.95) - 1)]

    print("V4 GraphRAG evaluation")
    print("-" * 72)
    print(f"entities={overview['entity_count']}  relations={overview['relation_count']}")
    for name, passed in checks.items():
        print(f"{name}={'passed' if passed else 'failed'}")
    print("-" * 72)
    print(f"entity_recall={entity_recall:.0%}")
    print(f"relation_recall={relation_recall:.0%}")
    print(f"structural_checks={structural_score:.0%}")
    print(f"avg_graph_latency_ms={statistics.mean(latencies):.2f}")
    print(f"p95_graph_latency_ms={p95_latency_ms:.2f}")

    passed = (
        entity_recall >= QUALITY_GATES["entity_recall"]
        and relation_recall >= QUALITY_GATES["relation_recall"]
        and structural_score >= QUALITY_GATES["structural_checks"]
        and p95_latency_ms <= QUALITY_GATES["p95_graph_latency_ms"]
    )
    print(f"quality_gate={'passed' if passed else 'failed'}")
    print(f"thresholds=entity>=90%, relation>=90%, structural=100%, p95<={QUALITY_GATES['p95_graph_latency_ms']:.0f}ms")
    return 0 if passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
