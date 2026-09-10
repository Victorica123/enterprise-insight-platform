"""Recovery checks against the dedicated localhost production-pilot Compose stack.

Stops only one named dependency at a time and always starts it again in finally.
AI remains mock/local. Results are deliberately separate from external AI/SLO claims.
"""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import time
from pathlib import Path

from local_acceptance import SAMPLE_MP4, multipart_file, request_json
from local_oidc import login

ROOT = Path(__file__).resolve().parents[1]
MEDIA = "http://127.0.0.1:18081"
AGENT = "http://127.0.0.1:18000"


def compose(*args):
    base = ["docker", "compose", "--env-file", "runtime/local-prod/.env", "-f", "compose.local-prod.yml"]
    if not shutil.which("docker") and os.name == "nt":
        base = ["wsl", "-d", "Ubuntu-24.04", "-u", "root", "--cd",
                "/mnt/d/Code Station/enterprise-insight-platform", "--", *base]
    completed = subprocess.run([*base, *args], cwd=ROOT, capture_output=True, timeout=90)
    if completed.returncode:
        raise RuntimeError("Compose operation failed: " + " ".join(args[:2]))
    return completed.stdout


def credentials():
    values = dict(line.split("=", 1) for line in (ROOT / "runtime/local-prod/load.env").read_text().splitlines() if "=" in line)
    return values["E2E_OIDC_USERNAME"], values["E2E_OIDC_PASSWORD"]


def token():
    session, _ = login(*credentials())
    return session["token"]


def upload(bearer, label):
    body, content_type = multipart_file("file", label + ".mp4", SAMPLE_MP4 + label.encode())
    status, result = request_json(MEDIA + "/api/media/upload/file", method="POST", token=bearer, body=body, content_type=content_type)
    if status != 200 or not result.get("data", {}).get("taskId"):
        raise RuntimeError(f"Upload was not accepted: {status}")
    return result["data"]["taskId"]


def wait_task(task_id, bearer, timeout=240):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        status, envelope = request_json(MEDIA + "/api/workflow/tasks/" + task_id, token=bearer)
        task = envelope.get("data", {})
        if status == 200 and task.get("status") == "COMPLETED":
            return task
        if task.get("status") == "FAILED":
            raise RuntimeError("Accepted workflow finished FAILED")
        time.sleep(1)
    raise TimeoutError("Accepted workflow failed to drain")


def wait_evidence(task, bearer, timeout=120):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        status, result = request_json(AGENT + "/chat", method="POST", token=bearer, payload={
            "question": task["fileName"] + " 的视频内容是什么？", "answer_mode": "local",
            "retriever_mode": "keyword", "workflow_mode": "standard", "asset_ids": [task["videoId"]],
        })
        if status == 200 and any(source.get("asset_id") == task["videoId"] for source in result.get("sources", [])):
            return
        time.sleep(1)
    raise TimeoutError("Outbox did not deliver searchable evidence")


def wait_health(base, path):
    for _ in range(90):
        try:
            status, _ = request_json(base + path)
            if status == 200:
                return
        except RuntimeError:
            pass
        time.sleep(1)
    raise TimeoutError("Dependency recovery did not restore health")


def main():
    results = []
    bearer = token()
    seed = wait_task(upload(bearer, "restart-seed-" + str(time.time_ns())), bearer)
    wait_evidence(seed, bearer)
    for dependency in ("agent", "rocketmq-broker", "minio", "redis", "mysql"):
        entry = {"dependency": dependency, "result": "FAIL"}
        try:
            bearer = token()
            compose("stop", dependency)
            try:
                if dependency in ("agent", "rocketmq-broker"):
                    task_id = upload(bearer, "fault-" + dependency + "-" + str(time.time_ns()))
                    # Give the dispatcher a chance to encounter the unavailable dependency.
                    time.sleep(3)
                    entry["accepted_task_id"] = task_id
                else:
                    path = "/api/workflow/tasks/" + seed["taskId"]
                    try:
                        status, _ = request_json(MEDIA + path, token=bearer)
                        entry["during_outage_http_status"] = status
                    except RuntimeError:
                        entry["during_outage_http_status"] = "timeout_or_disconnect"
                    if dependency == "minio":
                        # Upload exercises the actual object-storage write, not just SQL.
                        try:
                            accepted = upload(bearer, "minio-outage-" + str(time.time_ns()))
                            entry["accepted_task_id"] = accepted
                        except RuntimeError:
                            entry["object_write"] = "rejected_while_unavailable"
            finally:
                compose("start", dependency)
            wait_health(AGENT, "/health")
            wait_health(MEDIA, "/actuator/health")
            bearer = token()
            recovered = wait_task(entry.get("accepted_task_id", seed["taskId"]), bearer)
            wait_evidence(recovered, bearer)
            if dependency == "minio":
                recovered = wait_task(upload(bearer, "minio-recovered-" + str(time.time_ns())), bearer)
                wait_evidence(recovered, bearer)
            entry["result"] = "PASS"
        except Exception as error:
            entry["error"] = str(error)
        results.append(entry)
        print(json.dumps(entry), flush=True)
    output = ROOT / "runtime/local-prod/results/dependency-recovery.json"
    output.write_text(json.dumps(results, indent=2), encoding="utf-8")
    return 0 if all(item["result"] == "PASS" for item in results) else 1


if __name__ == "__main__":
    raise SystemExit(main())
