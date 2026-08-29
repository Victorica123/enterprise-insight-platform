from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path


def find_repository(start: Path) -> Path | None:
    current = start.resolve()
    for candidate in (current, *current.parents):
        if (
            (candidate / "knowledge" / "INDEX.md").is_file()
            and (candidate / "scripts" / "knowledge_index.py").is_file()
        ):
            return candidate
    return None


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Query the Enterprise Insight Platform semantic knowledge index."
    )
    parser.add_argument("query", help="Task, question or concept to retrieve.")
    parser.add_argument("--top-k", type=int, default=5)
    parser.add_argument("--json", action="store_true")
    parser.add_argument("--repo", type=Path, help="Repository root; defaults to searching from cwd.")
    args = parser.parse_args()

    repository = args.repo.resolve() if args.repo else find_repository(Path.cwd())
    if repository is None:
        print(
            "Enterprise Insight Platform repository not found. Run inside the repository or pass --repo.",
            file=sys.stderr,
        )
        return 2
    command = [
        sys.executable,
        str(repository / "scripts" / "knowledge_index.py"),
        "--root",
        str(repository),
        "query",
        args.query,
        "--top-k",
        str(max(1, min(args.top_k, 20))),
    ]
    if args.json:
        command.append("--json")
    return subprocess.run(command, cwd=repository, check=False).returncode


if __name__ == "__main__":
    raise SystemExit(main())
