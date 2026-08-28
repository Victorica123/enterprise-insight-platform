"""Reset the local database to a deterministic demo state.

演示/评测前先跑这个脚本，保证知识库、图谱、工单和监控面板都处于已知状态：

    python scripts/seed_demo.py            # 重置并灌入演示语料
    python scripts/seed_demo.py --no-traffic   # 只灌语料，不生成监控数据

之所以需要它：离线门禁（evaluate_v2/v4）直接读开发库，库里多一份无关文档
就可能让"该拒答"的用例变成"答了"。种子脚本让这个前置条件变成可复现的一步。
"""

from __future__ import annotations

import argparse
from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[1]
API_DIR = ROOT / "apps" / "api"
sys.path.insert(0, str(API_DIR))

from app.database import init_db, list_document_rows  # noqa: E402
from app.document_parser import parse_document  # noqa: E402
from app.graph_store import get_graph_overview, init_graph_store, rebuild_graph  # noqa: E402
from app.rag import delete_document, ingest_document  # noqa: E402
from app.ticket_store import create_ticket, delete_ticket, init_ticket_store, list_tickets  # noqa: E402


# 演示语料：字段连排的脏文本，用于展示图谱抽取对真实 PDF 的兼容
CORPUS = [ROOT / "docs" / "sample-project-delay-cn.pdf"]

DEMO_TICKETS = [
    {
        "title": "客户A项目延期跟进",
        "description": "测试环境部署失败导致交付推迟，需要确认新的交付计划并向客户提交书面风险说明。",
        "status": "open",
        "priority": "high",
        "assignee": "李四",
        "risk_level": "high",
    },
    {
        "title": "集成方案评审排期",
        "description": "集成方案尚未按时准备完成，需要安排一次评审并锁定负责人。",
        "status": "in_progress",
        "priority": "medium",
        "assignee": "王五",
        "risk_level": "medium",
    },
]

# 生成监控面板数据：既有能答的，也有该拒答的，让 /metrics 和失败回放都非空
DEMO_TRAFFIC = [
    "甲方客户A的项目为什么延期？",
    "项目负责人是谁？",
    "合同里对延期有什么风险约定？",
    "火星基地的氧气供应方案是什么？",
]


def clear_documents() -> int:
    rows = list_document_rows()
    for row in rows:
        delete_document(row["id"])
    return len(rows)


def clear_tickets() -> int:
    tickets = list_tickets()
    for ticket in tickets:
        delete_ticket(ticket.ticket_id)
    return len(tickets)


def load_corpus() -> list[str]:
    loaded: list[str] = []
    for path in CORPUS:
        if not path.exists():
            print(f"  ! 缺少语料文件，已跳过：{path}")
            continue
        content = parse_document(filename=path.name, raw=path.read_bytes())
        result = ingest_document(filename=path.name, content=content)
        loaded.append(f"{path.name}（{result.chunk_count} chunk）")
    return loaded


def generate_traffic() -> int:
    """走真实 /chat 端点产生指标与日志，保证监控面板和失败回放都有数据。"""
    try:
        from fastapi.testclient import TestClient

        from app.main import app
    except ImportError as exc:  # pragma: no cover - 仅在缺少 httpx 时触发
        print(f"  ! 跳过监控数据生成（{exc}）。安装 requirements-dev.txt 后可用。")
        return 0

    client = TestClient(app)
    recorded = 0
    for question in DEMO_TRAFFIC:
        response = client.post(
            "/chat",
            json={"question": question, "answer_mode": "local", "retriever_mode": "hybrid"},
        )
        if response.status_code != 200:
            print(f"  ! /chat 返回 {response.status_code}：{question}")
            continue
        recorded += 1
        log_id = response.json().get("log_id")
        # 给第一条打个正向反馈，让满意度指标非空
        if recorded == 1 and log_id:
            client.post(f"/chat-logs/{log_id}/feedback", json={"rating": "up", "note": "seed"})
    return recorded


def main() -> int:
    parser = argparse.ArgumentParser(description="Reset the demo database to a known state.")
    parser.add_argument(
        "--no-traffic",
        action="store_true",
        help="只灌语料和工单，不生成监控面板数据",
    )
    args = parser.parse_args()

    init_db()
    init_ticket_store()
    init_graph_store()

    print("1/4 清空旧数据")
    print(f"  - 删除文档 {clear_documents()} 份（含图谱与 chunk 级联清理）")
    print(f"  - 删除工单 {clear_tickets()} 条")

    print("2/4 灌入演示语料")
    for item in load_corpus():
        print(f"  - {item}")

    print("3/4 重建图谱与工单")
    for ticket in DEMO_TICKETS:
        created = create_ticket(**ticket)
        print(f"  - 工单 {created.ticket_id}：{created.title}")
    stats = rebuild_graph()
    print(f"  - 图谱：{stats['entity_count']} 实体 / {stats['relation_count']} 关系（{stats['duration_ms']}ms）")

    if args.no_traffic:
        print("4/4 跳过监控数据生成（--no-traffic）")
    else:
        print("4/4 生成监控数据")
        print(f"  - 已记录 {generate_traffic()} 次 /chat 请求（含 1 条应拒答用例供失败回放演示）")

    overview = get_graph_overview()
    print()
    print("演示环境就绪：")
    print(f"  文档 {len(list_document_rows())} 份 · 工单 {len(list_tickets())} 条 · 图谱实体 {overview['entity_count']} 个")
    print("  启动后端：cd apps/api && uvicorn app.main:app --reload --port 8000")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
