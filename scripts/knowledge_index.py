from __future__ import annotations

import argparse
import base64
import hashlib
import json
import math
import re
import sys
from pathlib import Path
from typing import Any

INDEX_VERSION = "enterprise-insight-knowledge-index-v3"
CHUNKING_ALGORITHM = "markdown-heading-body-1800-v2"
EMBEDDING_ALGORITHM = "hash-ngram-topic-embedding-v1"
EMBEDDING_DIMENSION = 192
VECTOR_ENCODING = "signed-int8-base64-v1"
MAX_CHUNK_CHARS = 1800
MAX_CACHE_ENTRIES = 128

ROOT = Path(__file__).resolve().parents[1]
INDEX_PATH = ROOT / "knowledge" / "generated" / "SEMANTIC_INDEX.json"
CACHE_PATH = ROOT / ".codex-cache" / "enterprise-insight" / "knowledge-query-cache.json"

_LATIN_TERM = re.compile(r"[a-z0-9][a-z0-9_.:/-]*", re.IGNORECASE)
_CJK_SEQUENCE = re.compile(r"[\u3400-\u9fff]+")
_SPACE = re.compile(r"\s+")

# Domain aliases add a small semantic layer without a model download. They map
# Chinese/English terms used across product, code and operations to stable topic
# features. The committed index therefore remains deterministic and CI-friendly.
TOPIC_ALIASES: dict[str, tuple[str, ...]] = {
    "identity": (
        "jwt", "auth", "authentication", "identity", "workspace", "tenant", "owner",
        "身份", "鉴权", "租户", "空间", "成员", "权限", "隔离", "邀请码",
    ),
    "media": (
        "media", "video", "upload", "transcript", "playback", "ffmpeg", "视频",
        "媒体", "上传", "转写", "播放", "时间戳",
    ),
    "agent": (
        "agent", "analysis", "rag", "workflow", "checkpoint", "prd", "智能体",
        "分析", "检索", "工作流", "检查点", "需求",
    ),
    "evidence": (
        "evidence", "citation", "source", "proof", "证据", "引用", "来源", "回放",
    ),
    "embedding": (
        "embedding", "vector", "semantic", "rerank", "rrf", "向量", "语义", "重排",
        "混合检索",
    ),
    "cache": (
        "cache", "kv", "revision", "fingerprint", "缓存", "增量", "指纹", "版本",
        "复用", "失效",
    ),
    "governance": (
        "approval", "audit", "publish", "immutable", "four-eyes", "审批", "审计",
        "发布", "四眼", "不可变", "工单",
    ),
    "integration": (
        "contract", "event", "outbox", "idempotent", "retry", "契约", "事件", "幂等",
        "重试", "投递",
    ),
    "operations": (
        "operations", "deploy", "backup", "restore", "docker", "localhost", "运维",
        "部署", "备份", "恢复", "本地验收",
    ),
    "quality": (
        "quality", "test", "eval", "gate", "slo", "质量", "测试", "评测", "门禁",
        "验收",
    ),
    "frontend": (
        "react", "web", "vite", "typescript", "ui", "frontend", "前端", "界面",
        "工作台",
    ),
}


def sha256_text(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def normalized_text(value: str) -> str:
    return _SPACE.sub(" ", value.strip().lower())


def source_paths(root: Path = ROOT) -> list[Path]:
    candidates: set[Path] = set()
    for relative in ("README.md", "AGENTS.md"):
        path = root / relative
        if path.is_file():
            candidates.add(path)
    for pattern in (
        "knowledge/**/*.md",
        "docs/**/*.md",
        "contracts/**/*.json",
        "skills/enterprise-insight-maintainer/SKILL.md",
        "skills/enterprise-insight-maintainer/references/**/*.md",
    ):
        candidates.update(path for path in root.glob(pattern) if path.is_file())
    return sorted(
        path
        for path in candidates
        if path.name != "SEMANTIC_INDEX.json"
        and not any(
            part.lower() in {"node_modules", "target", "dist", ".git", "archive"}
            for part in path.parts
        )
    )


def source_manifest(root: Path = ROOT) -> list[dict[str, str]]:
    manifest: list[dict[str, str]] = []
    for path in source_paths(root):
        text = path.read_text(encoding="utf-8", errors="ignore")
        manifest.append(
            {
                "path": path.relative_to(root).as_posix(),
                "sha256": sha256_text(text),
            }
        )
    return manifest


def corpus_revision(manifest: list[dict[str, str]]) -> str:
    payload = json.dumps(
        {
            "index_version": INDEX_VERSION,
            "chunking": CHUNKING_ALGORITHM,
            "algorithm": EMBEDDING_ALGORITHM,
            "dimension": EMBEDDING_DIMENSION,
            "vector_encoding": VECTOR_ENCODING,
            "sources": manifest,
        },
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    )
    return sha256_text(payload)


def _split_section(
    lines: list[str], start_line: int, heading: str
) -> list[dict[str, Any]]:
    chunks: list[dict[str, Any]] = []
    buffer: list[str] = []
    buffer_start = start_line
    char_count = 0

    def flush(end_line: int) -> None:
        nonlocal buffer, char_count, buffer_start
        content = "\n".join(buffer).strip()
        has_body = any(
            line.strip() and not line.strip().startswith("#") for line in buffer
        )
        if content and has_body:
            chunks.append(
                {
                    "heading": heading,
                    "start_line": buffer_start,
                    "end_line": end_line,
                    "content": content,
                }
            )
        buffer = []
        char_count = 0

    for offset, line in enumerate(lines):
        line_number = start_line + offset
        projected = char_count + len(line) + 1
        if buffer and projected > MAX_CHUNK_CHARS:
            flush(line_number - 1)
            buffer_start = line_number
        buffer.append(line)
        char_count += len(line) + 1
    flush(start_line + len(lines) - 1)
    return chunks


def chunk_document(relative_path: str, text: str) -> list[dict[str, Any]]:
    lines = text.splitlines()
    if not lines:
        return []

    sections: list[tuple[int, int, str]] = []
    section_start = 1
    heading = Path(relative_path).stem
    for index, line in enumerate(lines, start=1):
        stripped = line.strip()
        if stripped.startswith("#") and stripped.lstrip("#").strip():
            if index > section_start:
                sections.append((section_start, index - 1, heading))
            section_start = index
            heading = stripped.lstrip("#").strip()
    sections.append((section_start, len(lines), heading))

    chunks: list[dict[str, Any]] = []
    for start, end, section_heading in sections:
        chunks.extend(_split_section(lines[start - 1 : end], start, section_heading))
    return chunks


def _topic_features(text: str) -> list[tuple[str, float]]:
    lowered = text.lower()
    features: list[tuple[str, float]] = []
    for topic, aliases in TOPIC_ALIASES.items():
        if any(alias in lowered for alias in aliases):
            features.append((f"topic:{topic}", 3.0))
    return features


def embedding_features(text: str) -> list[tuple[str, float]]:
    lowered = normalized_text(text)
    features: list[tuple[str, float]] = []
    features.extend((term, 1.4) for term in _LATIN_TERM.findall(lowered))
    for sequence in _CJK_SEQUENCE.findall(lowered):
        features.extend((character, 0.25) for character in sequence)
        for size, weight in ((2, 1.0), (3, 1.25)):
            features.extend(
                (sequence[index : index + size], weight)
                for index in range(max(0, len(sequence) - size + 1))
            )
    features.extend(_topic_features(lowered))
    return features


def build_embedding(text: str, dimension: int = EMBEDDING_DIMENSION) -> list[float]:
    vector = [0.0] * dimension
    for term, weight in embedding_features(text):
        digest = hashlib.sha256(term.encode("utf-8")).digest()
        index = int.from_bytes(digest[:4], "big") % dimension
        sign = 1.0 if digest[4] % 2 == 0 else -1.0
        vector[index] += sign * weight
    norm = math.sqrt(sum(value * value for value in vector))
    if norm == 0:
        return vector
    return [round(value / norm, 8) for value in vector]


def cosine_similarity(left: list[float], right: list[float]) -> float:
    if not left or len(left) != len(right):
        return 0.0
    dot = sum(a * b for a, b in zip(left, right, strict=False))
    left_norm = math.sqrt(sum(value * value for value in left))
    right_norm = math.sqrt(sum(value * value for value in right))
    if left_norm == 0 or right_norm == 0:
        return 0.0
    return dot / (left_norm * right_norm)


def encode_vector(vector: list[float]) -> str:
    quantized = [max(-127, min(127, round(value * 127))) for value in vector]
    return base64.b64encode(bytes(value % 256 for value in quantized)).decode("ascii")


def decode_vector(raw: str) -> list[float]:
    try:
        values = base64.b64decode(raw.encode("ascii"), validate=True)
    except (ValueError, UnicodeError):
        return []
    return [(value if value < 128 else value - 256) / 127.0 for value in values]


def build_index(
    root: Path = ROOT, previous: dict[str, Any] | None = None
) -> tuple[dict[str, Any], dict[str, int]]:
    manifest = source_manifest(root)
    previous = previous or {}
    can_reuse = (
        previous.get("index_version") == INDEX_VERSION
        and previous.get("embedding", {}).get("algorithm") == EMBEDDING_ALGORITHM
        and previous.get("embedding", {}).get("dimension") == EMBEDDING_DIMENSION
        and previous.get("embedding", {}).get("encoding") == VECTOR_ENCODING
    )
    previous_vectors = {
        chunk.get("fingerprint"): chunk.get("vector_b64")
        for chunk in previous.get("chunks", [])
        if can_reuse and chunk.get("fingerprint") and chunk.get("vector_b64")
    }

    chunks: list[dict[str, Any]] = []
    reused = 0
    computed = 0
    for source in manifest:
        path = root / source["path"]
        text = path.read_text(encoding="utf-8", errors="ignore")
        for ordinal, raw_chunk in enumerate(chunk_document(source["path"], text)):
            embedding_input = (
                f"{source['path']}\n{raw_chunk['heading']}\n{raw_chunk['content']}"
            )
            fingerprint = sha256_text(embedding_input)
            vector_b64 = previous_vectors.get(fingerprint)
            if vector_b64 is None:
                vector_b64 = encode_vector(build_embedding(embedding_input))
                computed += 1
            else:
                reused += 1
            chunks.append(
                {
                    "id": sha256_text(
                        f"{source['path']}:{raw_chunk['start_line']}:{ordinal}:{fingerprint}"
                    )[:20],
                    "path": source["path"],
                    "heading": raw_chunk["heading"],
                    "start_line": raw_chunk["start_line"],
                    "end_line": raw_chunk["end_line"],
                    "fingerprint": fingerprint,
                    "preview": normalized_text(raw_chunk["content"])[:320],
                    "vector_b64": vector_b64,
                }
            )

    data = {
        "index_version": INDEX_VERSION,
        "corpus_revision": corpus_revision(manifest),
        "embedding": {
            "algorithm": EMBEDDING_ALGORITHM,
            "dimension": EMBEDDING_DIMENSION,
            "encoding": VECTOR_ENCODING,
            "model_download_required": False,
        },
        "chunking": {
            "algorithm": CHUNKING_ALGORITHM,
            "max_chunk_chars": MAX_CHUNK_CHARS,
        },
        "sources": manifest,
        "chunks": chunks,
    }
    return data, {"sources": len(manifest), "chunks": len(chunks), "reused": reused, "computed": computed}


def render_index(data: dict[str, Any]) -> str:
    return json.dumps(data, ensure_ascii=False, indent=2, sort_keys=True) + "\n"


def load_json(path: Path) -> dict[str, Any]:
    if not path.is_file():
        return {}
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return value if isinstance(value, dict) else {}


def update_index(root: Path = ROOT, check: bool = False) -> tuple[bool, dict[str, int]]:
    index_path = root / "knowledge" / "generated" / "SEMANTIC_INDEX.json"
    previous = load_json(index_path)
    expected, stats = build_index(root, previous)
    rendered = render_index(expected)
    if check:
        actual = index_path.read_text(encoding="utf-8") if index_path.is_file() else ""
        return actual == rendered, stats
    index_path.parent.mkdir(parents=True, exist_ok=True)
    index_path.write_text(rendered, encoding="utf-8", newline="\n")
    return True, stats


def _cache_key(data: dict[str, Any], query: str, top_k: int) -> str:
    payload = json.dumps(
        {
            "revision": data["corpus_revision"],
            "algorithm": data["embedding"]["algorithm"],
            "query_digest": sha256_text(normalized_text(query)),
            "top_k": top_k,
        },
        sort_keys=True,
        separators=(",", ":"),
    )
    return sha256_text(payload)


def search_index(data: dict[str, Any], query: str, top_k: int = 5) -> list[dict[str, Any]]:
    query_vector = build_embedding(query)
    ranked: list[tuple[float, dict[str, Any]]] = []
    for chunk in data.get("chunks", []):
        score = cosine_similarity(query_vector, decode_vector(chunk.get("vector_b64", "")))
        ranked.append((score, chunk))
    ranked.sort(key=lambda item: (item[0], item[1].get("path", "")), reverse=True)
    return [
        {
            "score": round(max(0.0, score), 6),
            "path": chunk["path"],
            "heading": chunk["heading"],
            "start_line": chunk["start_line"],
            "end_line": chunk["end_line"],
            "preview": chunk["preview"],
        }
        for score, chunk in ranked[: max(1, min(top_k, 20))]
    ]


def query_index(
    root: Path,
    query: str,
    top_k: int,
    cache_path: Path | None = None,
) -> tuple[list[dict[str, Any]], bool, str]:
    index_path = root / "knowledge" / "generated" / "SEMANTIC_INDEX.json"
    data = load_json(index_path)
    if not data:
        raise RuntimeError("semantic index is missing; run python scripts/update_knowledge.py")
    current_revision = corpus_revision(source_manifest(root))
    if data.get("corpus_revision") != current_revision:
        raise RuntimeError("semantic index is stale; run python scripts/update_knowledge.py")

    resolved_cache = cache_path or root / ".codex-cache" / "enterprise-insight" / "knowledge-query-cache.json"
    cache = load_json(resolved_cache)
    if cache.get("corpus_revision") != current_revision:
        cache = {"corpus_revision": current_revision, "entries": {}}
    entries = cache.setdefault("entries", {})
    key = _cache_key(data, query, top_k)
    cached = entries.get(key)
    if isinstance(cached, list):
        return cached, True, current_revision

    results = search_index(data, query, top_k)
    entries[key] = results
    while len(entries) > MAX_CACHE_ENTRIES:
        entries.pop(next(iter(entries)))
    resolved_cache.parent.mkdir(parents=True, exist_ok=True)
    resolved_cache.write_text(
        json.dumps(cache, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
        newline="\n",
    )
    return results, False, current_revision


def _print_results(results: list[dict[str, Any]], cache_hit: bool, revision: str) -> None:
    print(f"index_revision: {revision[:12]}")
    print(f"query_cache: {'hit' if cache_hit else 'miss'}")
    for index, result in enumerate(results, start=1):
        print(
            f"{index}. {result['path']}:{result['start_line']}-{result['end_line']} "
            f"[{result['heading']}] score={result['score']:.4f}"
        )
        print(f"   {result['preview']}")


def main() -> int:
    # Windows PowerShell can otherwise expose a legacy code page while the
    # Codex terminal expects UTF-8, turning Chinese previews into mojibake.
    for stream in (sys.stdout, sys.stderr):
        reconfigure = getattr(stream, "reconfigure", None)
        if callable(reconfigure):
            reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser(description="Build and query the project semantic knowledge index.")
    parser.add_argument("--root", type=Path, default=ROOT, help="Repository root.")
    subparsers = parser.add_subparsers(dest="command", required=True)
    subparsers.add_parser("build", help="Incrementally rebuild the generated index.")
    subparsers.add_parser("check", help="Fail when the generated index is stale.")
    subparsers.add_parser("stats", help="Show index metadata.")
    query_parser = subparsers.add_parser("query", help="Query the generated index.")
    query_parser.add_argument("query")
    query_parser.add_argument("--top-k", type=int, default=5)
    query_parser.add_argument("--json", action="store_true")
    args = parser.parse_args()
    root = args.root.resolve()

    if args.command in {"build", "check"}:
        passed, stats = update_index(root, check=args.command == "check")
        print(
            f"semantic-index sources={stats['sources']} chunks={stats['chunks']} "
            f"reused={stats['reused']} computed={stats['computed']}"
        )
        if not passed:
            print("Semantic knowledge drift detected. Run: python scripts/update_knowledge.py", file=sys.stderr)
            return 1
        return 0

    data = load_json(root / "knowledge" / "generated" / "SEMANTIC_INDEX.json")
    if args.command == "stats":
        if not data:
            print("Semantic index is missing.", file=sys.stderr)
            return 1
        print(
            json.dumps(
                {
                    "index_version": data.get("index_version"),
                    "corpus_revision": data.get("corpus_revision"),
                    "embedding": data.get("embedding"),
                    "chunking": data.get("chunking"),
                    "source_count": len(data.get("sources", [])),
                    "chunk_count": len(data.get("chunks", [])),
                },
                ensure_ascii=False,
                indent=2,
            )
        )
        return 0

    try:
        results, cache_hit, revision = query_index(root, args.query, args.top_k)
    except RuntimeError as exc:
        print(str(exc), file=sys.stderr)
        return 2
    if args.json:
        print(
            json.dumps(
                {"cache": "hit" if cache_hit else "miss", "revision": revision, "results": results},
                ensure_ascii=False,
                indent=2,
            )
        )
    else:
        _print_results(results, cache_hit, revision)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
