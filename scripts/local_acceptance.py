"""One-command localhost acceptance for the Media -> Agent evidence loop.

Starts both backend services on ephemeral loopback ports with H2, SQLite,
local files and mock AI implementations. It never needs DNS, a public server,
Docker, Redis, RocketMQ, object storage or an external model API.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
import socket
import shutil
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.request
import uuid


ROOT = Path(__file__).resolve().parents[1]
AGENT_DIR = ROOT / "services" / "agent-service"
MEDIA_DIR = ROOT / "services" / "media-service"
SHARED_SECRET = "01234567890123456789012345678901"
SERVICE_TOKEN = "local-acceptance-media-service-token"
MAVEN = shutil.which("mvn") or shutil.which("mvn.cmd")
JAVA = shutil.which("java") or shutil.which("java.exe")


def free_port() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def request_json(url: str, *, method: str = "GET", token: str | None = None,
                 payload: object | None = None, body: bytes | None = None,
                 content_type: str = "application/json", headers: dict[str, str] | None = None):
    data = body
    if payload is not None:
        data = json.dumps(payload).encode("utf-8")
    request_headers = dict(headers or {})
    if data is not None:
        request_headers["Content-Type"] = content_type
    if token:
        request_headers["Authorization"] = f"Bearer {token}"
    request = urllib.request.Request(url, data=data, method=method, headers=request_headers)
    with urllib.request.urlopen(request, timeout=20) as response:
        raw = response.read()
        return response.status, json.loads(raw) if raw else None


def wait_ready(url: str, process: subprocess.Popen, log_path: Path, timeout: float = 35) -> None:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if process.poll() is not None:
            raise RuntimeError(f"服务提前退出（code={process.returncode}），日志：{log_path}")
        try:
            with urllib.request.urlopen(url, timeout=1) as response:
                if response.status < 500:
                    return
        except (OSError, urllib.error.URLError):
            time.sleep(0.25)
    raise TimeoutError(f"等待本地服务超时：{url}，日志：{log_path}")


def multipart_file(field: str, filename: str, content: bytes) -> tuple[bytes, str]:
    boundary = f"----enterprise-insight-{uuid.uuid4().hex}"
    body = (
        f"--{boundary}\r\n"
        f'Content-Disposition: form-data; name="{field}"; filename="{filename}"\r\n'
        "Content-Type: video/mp4\r\n\r\n"
    ).encode() + content + f"\r\n--{boundary}--\r\n".encode()
    return body, f"multipart/form-data; boundary={boundary}"


def start(command: list[str], cwd: Path, env: dict[str, str], log_path: Path) -> tuple[subprocess.Popen, object]:
    log = log_path.open("w", encoding="utf-8")
    process = subprocess.Popen(command, cwd=cwd, env=env, stdout=log, stderr=subprocess.STDOUT)
    return process, log


def main() -> int:
    if not MAVEN or not JAVA:
        raise RuntimeError("本地验收需要 PATH 中可用的 Maven 与 Java（项目目标 JDK 17/18）。")
    agent_port, media_port = free_port(), free_port()
    with tempfile.TemporaryDirectory(prefix="enterprise-insight-acceptance-") as temp_raw:
        temp = Path(temp_raw)
        agent_log, media_log = temp / "agent.log", temp / "media.log"

        subprocess.run(
            [MAVEN, "-q", "-DskipTests", "package"], cwd=MEDIA_DIR, check=True,
        )
        jar = MEDIA_DIR / "target" / "video-platform-0.0.1-SNAPSHOT.jar"
        if not jar.exists():
            raise FileNotFoundError(f"Media Service jar 未生成：{jar}")

        agent_env = os.environ.copy()
        agent_env.update({
            "AGENT_AUTH_MODE": "jwt",
            "APP_ENV": "development",
            "SHARED_JWT_SECRET": SHARED_SECRET,
            "APP_JWT_ISSUER": "enterprise-insight",
            "APP_JWT_AUDIENCE": "enterprise-insight-api",
            "MEDIA_INGEST_SERVICE_TOKEN": SERVICE_TOKEN,
            "DEFAULT_ANSWER_MODE": "local",
            "RETRIEVER_MODE": "keyword",
            "EMBEDDING_MODEL": "",
            "RERANKER_MODEL": "",
            "AGENT_DATABASE_PATH": str(temp / "agent.sqlite3"),
        })
        media_env = os.environ.copy()
        media_env.update({
            "SERVER_PORT": str(media_port),
            "APP_JWT_SECRET": SHARED_SECRET,
            "APP_JWT_ISSUER": "enterprise-insight",
            "APP_JWT_AUDIENCE": "enterprise-insight-api",
            "APP_AGENT_INTEGRATION_ENABLED": "true",
            "AGENT_SERVICE_BASE_URL": f"http://127.0.0.1:{agent_port}",
            "MEDIA_INGEST_SERVICE_TOKEN": SERVICE_TOKEN,
            "APP_AGENT_DISPATCH_INTERVAL_MS": "200",
            "APP_STORAGE_BASE_PATH": str(temp / "media"),
            "APP_TRANSCRIPT_ENABLED": "false",
            "APP_SUMMARY_ENABLED": "false",
        })

        processes: list[tuple[subprocess.Popen, object]] = []
        try:
            processes.append(start(
                [sys.executable, "-m", "uvicorn", "app.main:app", "--host", "127.0.0.1", "--port", str(agent_port)],
                AGENT_DIR, agent_env, agent_log,
            ))
            wait_ready(f"http://127.0.0.1:{agent_port}/health", processes[-1][0], agent_log)
            processes.append(start(
                [JAVA, "-jar", str(jar), "--spring.profiles.active=h2"],
                MEDIA_DIR, media_env, media_log,
            ))
            wait_ready(f"http://127.0.0.1:{media_port}/actuator/health", processes[-1][0], media_log)

            username = f"acceptance-{uuid.uuid4().hex[:10]}"
            _, auth_envelope = request_json(
                f"http://127.0.0.1:{media_port}/api/auth/register", method="POST",
                payload={"username": username, "password": "local-pass-123"},
            )
            auth = auth_envelope["data"]
            assert auth["tenantId"] and auth["role"] == "admin"
            assert auth["workspaceType"] == "personal"
            token = auth["token"]

            upload_body, upload_type = multipart_file(
                "file", "local-acceptance.mp4", b"local-video-acceptance-content",
            )
            _, upload_envelope = request_json(
                f"http://127.0.0.1:{media_port}/api/media/upload/file", method="POST", token=token,
                body=upload_body, content_type=upload_type,
            )
            task_id = upload_envelope["data"]["taskId"]

            deadline = time.monotonic() + 20
            task = None
            while time.monotonic() < deadline:
                _, task_envelope = request_json(
                    f"http://127.0.0.1:{media_port}/api/workflow/tasks/{task_id}", token=token,
                )
                task = task_envelope["data"]
                if task["status"] in {"COMPLETED", "FAILED"}:
                    break
                time.sleep(0.2)
            assert task and task["status"] == "COMPLETED", task
            assert task["tenantId"] == auth["tenantId"]
            assert task["transcriptSegments"] and task["transcriptSegments"][0]["startMs"] == 0

            deadline = time.monotonic() + 15
            chat = None
            while time.monotonic() < deadline:
                _, chat = request_json(
                    f"http://127.0.0.1:{agent_port}/chat", method="POST", token=token,
                    payload={
                        "question": "local-acceptance.mp4 的视频内容是什么？",
                        "answer_mode": "local", "retriever_mode": "keyword", "workflow_mode": "standard",
                        "asset_ids": [task["videoId"]],
                    },
                )
                if any(source.get("source_type") == "video" for source in chat.get("sources", [])):
                    break
                time.sleep(0.25)
            video_sources = [source for source in chat["sources"] if source.get("source_type") == "video"]
            assert video_sources, chat
            source = video_sources[0]
            assert source["asset_id"] == task["videoId"] and source["start_ms"] == 0

            _, analysis = request_json(
                f"http://127.0.0.1:{agent_port}/analysis/sessions", method="POST", token=token,
                payload={"objective": "生成本地验收视频的需求 PRD", "asset_ids": [task["videoId"]]},
            )
            assert analysis["status"] == "WAITING_CONFIRMATION" and analysis["resume_token"]
            answer_defaults = {
                "decision_maker": "本地验收负责人",
                "acceptance_criteria": "主链路全部自动检查通过",
                "priority_rule": "阻塞主链路的问题优先",
                "evidence_scope": "仅使用本次上传视频",
            }
            answers = {question["question_id"]: answer_defaults[question["question_id"]]
                       for question in analysis["open_questions"]}
            _, analysis = request_json(
                f"http://127.0.0.1:{agent_port}/analysis/sessions/{analysis['session_id']}/confirm",
                method="POST", token=token,
                payload={"resume_token": analysis["resume_token"], "answers": answers},
            )
            assert analysis["status"] == "DRAFT_READY" and len(analysis["stages"]) == 6
            prd_evidence = analysis["prd"]["requirements"][0]["evidence"][0]
            assert prd_evidence["asset_id"] == task["videoId"] and prd_evidence["start_ms"] == 0

            _, publication = request_json(
                f"http://127.0.0.1:{agent_port}/analysis/sessions/{analysis['session_id']}/publication/request",
                method="POST", token=token,
            )
            assert publication["status"] == "PUBLISH_PENDING"
            assert publication["publication"]["policy"] == "OWNER_RECONFIRMATION"
            _, publication = request_json(
                f"http://127.0.0.1:{agent_port}/analysis/sessions/{analysis['session_id']}/publication/approve",
                method="POST", token=token,
                payload={
                    "request_id": publication["publication"]["request_id"],
                    "approval_token": publication["publication"]["approval_token"],
                    "confirmation": "PUBLISH",
                },
            )
            assert publication["status"] == "PUBLISHED"
            assert publication["prd"]["publication_status"] == "PUBLISHED"
            _, audit = request_json(
                f"http://127.0.0.1:{agent_port}/analysis/sessions/{analysis['session_id']}/audit",
                token=token,
            )
            assert [event["action"] for event in audit] == [
                "PUBLICATION_REQUESTED", "PUBLICATION_APPROVED",
            ]
            _, deliverables = request_json(
                f"http://127.0.0.1:{agent_port}/analysis/sessions/{analysis['session_id']}/deliverables",
                token=token,
            )
            assert len(deliverables["version"]["content_sha256"]) == 64
            candidate = deliverables["knowledge_candidates"][0]
            assert candidate["status"] == "PENDING"
            _, candidate = request_json(
                f"http://127.0.0.1:{agent_port}/analysis/sessions/{analysis['session_id']}"
                f"/knowledge-candidates/{candidate['candidate_id']}/decision",
                method="POST", token=token, payload={"approved": True},
            )
            assert candidate["status"] == "APPROVED"
            action_item = deliverables["action_items"][0]
            _, ticket_draft = request_json(
                f"http://127.0.0.1:{agent_port}/analysis/sessions/{analysis['session_id']}"
                f"/action-items/{action_item['action_item_id']}/ticket-draft",
                method="POST", token=token,
            )
            assert ticket_draft["action_item"]["status"] == "TICKET_PENDING_APPROVAL"
            _, ticket_approval = request_json(
                f"http://127.0.0.1:{agent_port}/pending-actions/{ticket_draft['pending_action_id']}/approve",
                method="POST", token=token, payload={"approved": True},
            )
            assert ticket_approval["status"] == "succeeded"
            _, settled_deliverables = request_json(
                f"http://127.0.0.1:{agent_port}/analysis/sessions/{analysis['session_id']}/deliverables",
                token=token,
            )
            settled_action = settled_deliverables["action_items"][0]
            assert settled_action["status"] == "TICKET_CREATED"
            assert settled_action["ticket_id"] == ticket_approval["result"]["ticket"]["ticket_id"]
            _, tickets = request_json(
                f"http://127.0.0.1:{agent_port}/tickets", token=token,
            )
            assert tickets["total"] == 1

            _, playback_envelope = request_json(
                f"http://127.0.0.1:{media_port}/api/media/video/{task_id}/playback-token", token=token,
            )
            stream_url = playback_envelope["data"]["streamUrl"]
            request = urllib.request.Request(
                f"http://127.0.0.1:{media_port}{stream_url}", headers={"Range": "bytes=0-3"},
            )
            with urllib.request.urlopen(request, timeout=10) as response:
                assert response.status == 206 and response.read() == b"loca"

            print(json.dumps({
                "result": "PASS",
                "network_scope": "localhost-only",
                "tenant_id": auth["tenantId"],
                "task_id": task_id,
                "asset_id": task["videoId"],
                "video_evidence": {"start_ms": source["start_ms"], "end_ms": source["end_ms"]},
                "checks": ["register_workspace", "jwt_tenant", "upload", "mock_transcript",
                           "outbox_delivery", "agent_retrieval", "timestamp_source",
                           "analysis_wait_resume", "evidence_prd", "publication_approval_audit",
                           "immutable_prd_snapshot", "knowledge_candidate_approval",
                           "action_item_ticket_approval",
                           "range_playback"],
            }, ensure_ascii=False, indent=2))
            return 0
        finally:
            for process, log in reversed(processes):
                if process.poll() is None:
                    process.terminate()
                    try:
                        process.wait(timeout=8)
                    except subprocess.TimeoutExpired:
                        process.kill()
                log.close()
            if sys.exc_info()[0] is not None:
                failure_dir = Path(tempfile.gettempdir()) / f"enterprise-insight-failure-{int(time.time())}"
                failure_dir.mkdir(parents=True, exist_ok=False)
                for source in (agent_log, media_log):
                    if source.exists():
                        shutil.copy2(source, failure_dir / source.name)
                print(f"Local acceptance logs preserved at: {failure_dir}", file=sys.stderr)


if __name__ == "__main__":
    raise SystemExit(main())
