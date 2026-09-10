"""In-process Agent soak with tracemalloc snapshots; no server or external API required."""

from __future__ import annotations

import argparse
import gc
import json
import os
import sys
import tempfile
import tracemalloc
from pathlib import Path

SCRIPT_PATH = Path(__file__).resolve()
DEFAULT_AGENT_DIR = (
    SCRIPT_PATH.parents[2] / "services" / "agent-service"
    if len(SCRIPT_PATH.parents) > 2
    else Path.cwd()
)
AGENT_DIR = Path(os.getenv("AGENT_SOURCE_DIR", str(DEFAULT_AGENT_DIR))).resolve()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--iterations", type=int, default=2_000)
    parser.add_argument("--max-growth-mb", type=float, default=24.0)
    args = parser.parse_args()

    with tempfile.TemporaryDirectory(prefix="enterprise-insight-agent-memory-") as temp_dir:
        os.environ["AGENT_DATABASE_PATH"] = str(Path(temp_dir) / "agent.sqlite3")
        os.environ["AGENT_AUTH_MODE"] = "development"
        os.environ["APP_ENV"] = "development"
        os.environ["DEFAULT_ANSWER_MODE"] = "local"
        os.environ["RETRIEVER_MODE"] = "keyword"
        os.environ["EMBEDDING_MODEL"] = ""
        os.environ["RERANKER_MODEL"] = ""
        sys.path.insert(0, str(AGENT_DIR))

        tracemalloc.start(25)
        from app.main import app
        from fastapi.testclient import TestClient

        headers = {"X-User-Role": "admin", "X-User-Id": "memory-probe"}
        with TestClient(app) as client:
            upload = client.post(
                "/documents",
                headers=headers,
                files={"file": ("memory-probe.md", b"# Reliability\nqueue lease evidence approval", "text/markdown")},
            )
            upload.raise_for_status()
            payload = {
                "question": "What reliability evidence is available?",
                "answer_mode": "local",
                "retriever_mode": "keyword",
                "workflow_mode": "standard",
            }
            for _ in range(100):
                client.post("/chat", headers=headers, json=payload).raise_for_status()
            gc.collect()
            baseline = tracemalloc.take_snapshot()

            for _ in range(args.iterations):
                client.post("/chat", headers=headers, json=payload).raise_for_status()

            gc.collect()
            final = tracemalloc.take_snapshot()

        growth_bytes = sum(stat.size_diff for stat in final.compare_to(baseline, "lineno"))
        current_bytes, peak_bytes = tracemalloc.get_traced_memory()
        top = [
            {"location": str(stat.traceback[0]), "size_diff": stat.size_diff, "count_diff": stat.count_diff}
            for stat in final.compare_to(baseline, "lineno")[:20]
        ]
        report = {
            "iterations": args.iterations,
            "growth_bytes": growth_bytes,
            "growth_mb": round(growth_bytes / 1024 / 1024, 3),
            "current_mb": round(current_bytes / 1024 / 1024, 3),
            "peak_mb": round(peak_bytes / 1024 / 1024, 3),
            "max_growth_mb": args.max_growth_mb,
            "top_growth": top,
        }
        print(json.dumps(report, ensure_ascii=False, indent=2))
        return 1 if growth_bytes > args.max_growth_mb * 1024 * 1024 else 0


if __name__ == "__main__":
    raise SystemExit(main())
