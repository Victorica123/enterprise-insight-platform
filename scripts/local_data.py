"""Backup, verify and restore the bind-mounted localhost data set.

Stop ``compose.local.yml`` before backup/restore so the H2 file is closed.
The Agent SQLite database is copied through SQLite's online backup API.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import sqlite3
import tempfile
from contextlib import closing
from datetime import UTC, datetime
from pathlib import Path
from zipfile import ZIP_DEFLATED, ZipFile

ROOT = Path(__file__).resolve().parents[1]
RUNTIME = (ROOT / "runtime").resolve()
BACKUPS = (ROOT / "backups").resolve()
MANIFEST = "manifest.json"


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def ensure_databases_closed() -> None:
    locks = list((RUNTIME / "media" / "db").glob("*.lock.db")) if RUNTIME.exists() else []
    if locks:
        raise RuntimeError(
            "Media H2 is still open. Run scripts/stop_local.ps1 before backup or restore."
        )


def stage_runtime(stage: Path) -> Path:
    staged_runtime = stage / "runtime"
    staged_runtime.mkdir(parents=True)
    if not RUNTIME.exists():
        return staged_runtime

    agent_db = RUNTIME / "agent" / "knowledge_base.sqlite3"
    excluded = {agent_db, Path(f"{agent_db}-wal"), Path(f"{agent_db}-shm")}
    for source in RUNTIME.rglob("*"):
        if not source.is_file() or source.resolve() in {item.resolve() for item in excluded}:
            continue
        if source.name.endswith(".lock.db"):
            continue
        destination = staged_runtime / source.relative_to(RUNTIME)
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, destination)

    if agent_db.exists():
        destination = staged_runtime / agent_db.relative_to(RUNTIME)
        destination.parent.mkdir(parents=True, exist_ok=True)
        with (
            closing(sqlite3.connect(agent_db)) as source,
            closing(sqlite3.connect(destination)) as target,
        ):
            source.backup(target)
            target.commit()
            result = target.execute("pragma quick_check").fetchone()
            if not result or result[0] != "ok":
                raise RuntimeError("Agent SQLite backup did not pass quick_check.")
    return staged_runtime


def write_backup(output: Path) -> Path:
    ensure_databases_closed()
    output = output.resolve()
    output.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="enterprise-insight-backup-") as raw:
        stage = Path(raw)
        staged_runtime = stage_runtime(stage)
        files = [path for path in staged_runtime.rglob("*") if path.is_file()]
        manifest = {
            "format": 1,
            "created_at": datetime.now(UTC).isoformat(),
            "files": [{
                "path": path.relative_to(stage).as_posix(),
                "size": path.stat().st_size,
                "sha256": sha256(path),
            } for path in sorted(files)],
        }
        (stage / MANIFEST).write_text(
            json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8",
        )
        with ZipFile(output, "w", ZIP_DEFLATED) as archive:
            archive.write(stage / MANIFEST, MANIFEST)
            for path in files:
                archive.write(path, path.relative_to(stage).as_posix())
    return output


def verify_backup(archive_path: Path) -> dict[str, object]:
    archive_path = archive_path.resolve()
    with tempfile.TemporaryDirectory(prefix="enterprise-insight-verify-") as raw:
        stage = Path(raw).resolve()
        with ZipFile(archive_path) as archive:
            for member in archive.infolist():
                target = (stage / member.filename).resolve()
                if stage not in target.parents and target != stage:
                    raise RuntimeError(f"Unsafe archive path: {member.filename}")
            archive.extractall(stage)
        manifest = json.loads((stage / MANIFEST).read_text(encoding="utf-8"))
        if manifest.get("format") != 1 or not isinstance(manifest.get("files"), list):
            raise RuntimeError("Unsupported or malformed backup manifest.")
        for item in manifest["files"]:
            path = (stage / item["path"]).resolve()
            if stage not in path.parents or not path.is_file():
                raise RuntimeError(f"Missing backup file: {item['path']}")
            if path.stat().st_size != item["size"] or sha256(path) != item["sha256"]:
                raise RuntimeError(f"Backup checksum mismatch: {item['path']}")
        agent_db = stage / "runtime" / "agent" / "knowledge_base.sqlite3"
        if agent_db.exists():
            with closing(sqlite3.connect(agent_db)) as conn:
                result = conn.execute("pragma quick_check").fetchone()
                if not result or result[0] != "ok":
                    raise RuntimeError("Agent SQLite backup failed quick_check.")
        return manifest


def restore_backup(archive_path: Path, *, force: bool) -> tuple[Path, Path | None]:
    ensure_databases_closed()
    verify_backup(archive_path)
    existing = RUNTIME.exists() and any(RUNTIME.rglob("*"))
    safety_backup: Path | None = None
    if existing and not force:
        raise RuntimeError("Runtime data already exists. Re-run restore with --force after review.")
    if existing:
        timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
        safety_backup = write_backup(BACKUPS / f"pre-restore-{timestamp}.zip")

    with tempfile.TemporaryDirectory(prefix="enterprise-insight-restore-") as raw:
        stage = Path(raw).resolve()
        with ZipFile(archive_path.resolve()) as archive:
            archive.extractall(stage)
        restored = stage / "runtime"
        if RUNTIME.exists():
            shutil.rmtree(RUNTIME)
        shutil.copytree(restored, RUNTIME)
    return RUNTIME, safety_backup


def main() -> int:
    parser = argparse.ArgumentParser(description="Manage localhost Enterprise Insight data.")
    subparsers = parser.add_subparsers(dest="command", required=True)
    backup = subparsers.add_parser("backup")
    backup.add_argument("--output", type=Path)
    verify = subparsers.add_parser("verify")
    verify.add_argument("archive", type=Path)
    restore = subparsers.add_parser("restore")
    restore.add_argument("archive", type=Path)
    restore.add_argument("--force", action="store_true")
    args = parser.parse_args()

    if args.command == "backup":
        default = BACKUPS / f"local-{datetime.now().strftime('%Y%m%d-%H%M%S')}.zip"
        print(write_backup(args.output or default))
    elif args.command == "verify":
        manifest = verify_backup(args.archive)
        print(json.dumps({"status": "ok", "files": len(manifest["files"])}, ensure_ascii=False))
    else:
        restored, safety = restore_backup(args.archive, force=args.force)
        print(json.dumps({
            "status": "restored", "path": str(restored),
            "pre_restore_backup": str(safety) if safety else None,
        }, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
