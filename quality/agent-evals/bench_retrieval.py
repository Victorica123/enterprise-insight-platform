"""Before/after retrieval micro-benchmark on a synthetic corpus (optimisation plan evidence).

Usage:
    python quality/agent-evals/bench_retrieval.py --chunks 2000
    python quality/agent-evals/bench_retrieval.py --chunks 2000 --app-root <dir containing app/>

To reproduce the "before" column, export the pre-optimisation tree and point
``--app-root`` at it:

    git archive 7195dad services/agent-service/app | tar -x -C runtime/before-src
    python quality/agent-evals/bench_retrieval.py --app-root runtime/before-src/services/agent-service

Each run is one process, so the two trees never share modules.  Hash
embeddings only (no fastembed) and LLM router disabled: the same conditions as
CI.  The corpus is synthetic and single-tenant; the numbers show relative cost
of the retrieval hot path, not production throughput.
"""
from __future__ import annotations

import argparse
import json
import os
import random
import statistics
import sys
import tempfile
from pathlib import Path
from time import perf_counter
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
DEFAULT_APP_ROOT = ROOT / "services" / "agent-service"

parser = argparse.ArgumentParser()
parser.add_argument("--app-root", default=str(DEFAULT_APP_ROOT))
parser.add_argument("--chunks", type=int, default=2000)
parser.add_argument("--repeat", type=int, default=5)
args = parser.parse_args()

sys.path.insert(0, args.app_root)
os.environ.setdefault("LLM_ROUTER_ENABLED", "0")

from app.rag import ingest_document  # noqa: E402
from app.retrievers import RetrievalScope, get_retriever  # noqa: E402

CUSTOMERS = [f"客户{c}" for c in "ABCDEFGHJKLMNPQRSTUVWXYZ"]
PROJECTS = ["数据中台", "会员系统", "结算平台", "仓储改造", "门店巡检", "供应链协同", "移动端重构", "风控引擎"]
TOPICS = [
    "延期原因是测试环境部署失败", "合同约定延期超过十五天需提交风险说明", "项目负责人是李四",
    "验收标准包括性能压测通过", "供应商交付延误导致排期调整", "预算超支需要重新审批",
    "上线窗口定在季度末", "客户提出接口变更需求", "安全评审发现高危漏洞", "培训计划分三期完成",
    "数据迁移在夜间执行", "回滚方案已经演练", "监控告警接入统一平台", "工单积压需要增派人手",
    "服务等级协议要求可用性四个九", "灰度发布覆盖十个门店", "采购流程走公开招标", "运维交接文档缺失",
]
FILLER = ["会议纪要", "阶段汇报", "风险登记", "周报", "变更申请", "验收记录", "复盘总结", "需求澄清"]

random.seed(7)


def make_doc(i: int) -> tuple[str, str]:
    customer = random.choice(CUSTOMERS)
    project = random.choice(PROJECTS)
    lines = [f"{customer}{project}{random.choice(FILLER)}第{i}期。"]
    for _ in range(4):
        lines.append(f"{customer}的{project}：{random.choice(TOPICS)}，编号{random.randint(1000, 9999)}。")
    return f"{customer}-{project}-{i}.md", "".join(lines)


QUERIES = [
    f"{random.choice(CUSTOMERS)}的{random.choice(PROJECTS)}为什么延期？" for _ in range(10)
] + [
    f"{random.choice(CUSTOMERS)}{random.choice(PROJECTS)}的负责人是谁", "合同风险有哪些", "验收标准是什么",
    "供应商交付延误影响哪些项目", "安全评审发现了什么", "数据迁移什么时候执行", "哪些项目预算超支",
    "灰度发布覆盖范围", "监控告警怎么接入", "回滚方案演练过吗",
]


def bench(mode: str, scope: RetrievalScope | None, repeat: int) -> dict[str, float]:
    retriever = get_retriever(mode)
    retriever.search(QUERIES[:1], scope)  # warm the chunk cache after ingest
    samples: list[float] = []
    for _ in range(repeat):
        for query in QUERIES:
            started = perf_counter()
            retriever.search([query], scope)
            samples.append((perf_counter() - started) * 1000)
    samples.sort()
    return {
        "p50_ms": round(statistics.median(samples), 2),
        "p95_ms": round(samples[int(len(samples) * 0.95) - 1], 2),
        "mean_ms": round(statistics.fmean(samples), 2),
        "n": len(samples),
    }


def cold_reload(mode: str, scope: RetrievalScope | None) -> float:
    """Latency of the first search after a write bumps the revision (cache rebuild)."""
    ingest_document("bump.md", "客户Z的门店巡检周报。", tenant_id="legacy", owner_id="legacy", index_graph=False)
    started = perf_counter()
    get_retriever(mode).search(QUERIES[:1], scope)
    return round((perf_counter() - started) * 1000, 2)


with tempfile.TemporaryDirectory() as temp_dir, patch("app.database.DB_PATH", Path(temp_dir) / "bench.sqlite3"):
    ingest_started = perf_counter()
    for i in range(args.chunks):
        filename, content = make_doc(i)
        ingest_document(filename, content, tenant_id="legacy", owner_id="legacy", index_graph=False)
    ingest_ms = (perf_counter() - ingest_started) * 1000
    scope = RetrievalScope(tenant_id="legacy")
    result = {
        "app_root": args.app_root,
        "chunks": args.chunks,
        "ingest_total_ms": round(ingest_ms),
        "keyword": bench("keyword", scope, args.repeat),
        "hybrid": bench("hybrid", scope, args.repeat),
        "cold_reload_keyword_ms": cold_reload("keyword", scope),
        "cold_reload_hybrid_ms": cold_reload("hybrid", scope),
    }
print(json.dumps(result, ensure_ascii=False))
