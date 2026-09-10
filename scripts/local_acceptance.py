"""One-command localhost acceptance for the Media -> Agent evidence loop.

Starts both backend services on ephemeral loopback ports with H2, SQLite,
local files and mock AI implementations. It never needs DNS, a public server,
Docker, Redis, RocketMQ, object storage or an external model API.
"""

from __future__ import annotations

import http.client
import json
import os
import secrets
import shutil
import socket
import subprocess
import sys
import tempfile
import time
import uuid
from pathlib import Path
from typing import Any, TextIO
from urllib.parse import urlsplit, urlunsplit

ROOT = Path(__file__).resolve().parents[1]
AGENT_DIR = ROOT / "services" / "agent-service"
MEDIA_DIR = ROOT / "services" / "media-service"
MAVEN = shutil.which("mvn") or shutil.which("mvn.cmd")
JAVA = shutil.which("java") or shutil.which("java.exe")
SAMPLE_MP4 = b"\x00\x00\x00\x18ftypisom\x00\x00\x02\x00"


def free_port() -> int:
    try:
        with socket.socket() as sock:
            sock.bind(("127.0.0.1", 0))
            return int(sock.getsockname()[1])
    except OSError as exc:
        raise RuntimeError("Unable to allocate a localhost port") from exc


def http_request(
    url: str,
    *,
    method: str = "GET",
    body: bytes | None = None,
    headers: dict[str, str] | None = None,
    timeout: float = 20,
) -> tuple[int, bytes]:
    parsed_url = urlsplit(url)
    if parsed_url.scheme not in {"http", "https"}:
        raise ValueError(f"Only HTTP(S) URLs are allowed: {url}")
    if parsed_url.hostname not in {"127.0.0.1", "localhost"}:
        raise ValueError(f"Only localhost URLs are allowed: {url}")
    try:
        port = parsed_url.port
    except ValueError as exc:
        raise ValueError(f"Invalid localhost port in URL: {url}") from exc
    connection_type = (
        http.client.HTTPSConnection
        if parsed_url.scheme == "https"
        else http.client.HTTPConnection
    )
    connection = connection_type(parsed_url.hostname, port, timeout=timeout)
    path = urlunsplit(("", "", parsed_url.path or "/", parsed_url.query, ""))
    try:
        connection.request(method, path, body=body, headers=headers or {})
        response = connection.getresponse()
        return response.status, response.read()
    except (OSError, ValueError) as exc:
        raise RuntimeError(f"HTTP request failed for {url}") from exc
    finally:
        connection.close()


def request_json(
    url: str,
    *,
    method: str = "GET",
    token: str | None = None,
    payload: object | None = None,
    body: bytes | None = None,
    content_type: str = "application/json",
    headers: dict[str, str] | None = None,
) -> tuple[int, Any]:
    data = body
    if payload is not None:
        data = json.dumps(payload).encode("utf-8")
    request_headers = dict(headers or {})
    if data is not None:
        request_headers["Content-Type"] = content_type
    if token:
        request_headers["Authorization"] = f"Bearer {token}"
    status, raw = http_request(url, method=method, body=data, headers=request_headers)
    try:
        parsed = json.loads(raw) if raw else {}
    except json.JSONDecodeError as exc:
        raise RuntimeError(f"Invalid JSON response from {url}") from exc
    return status, parsed


def request_json_with_errors(url: str, **kwargs: Any) -> tuple[int, Any]:
    """Return JSON for both success and expected 4xx responses."""
    return request_json(url, **kwargs)


def wait_ready(
    url: str, process: subprocess.Popen | None, log_path: Path, timeout: float = 35
) -> None:
    if not url.startswith("http://127.0.0.1:"):
        raise ValueError(f"Readiness checks must target localhost: {url}")
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if process is not None and process.poll() is not None:
            raise RuntimeError(
                f"服务提前退出（code={process.returncode}），日志：{log_path}"
            )
        try:
            status, _ = http_request(url, timeout=1)
            if status < 500:
                return
        except RuntimeError:
            time.sleep(0.25)
    raise TimeoutError(f"等待本地服务超时：{url}，日志：{log_path}")


def multipart_file(field: str, filename: str, content: bytes) -> tuple[bytes, str]:
    boundary = f"----enterprise-insight-{uuid.uuid4().hex}"
    body = (
        (
            f"--{boundary}\r\n"
            f'Content-Disposition: form-data; name="{field}"; filename="{filename}"\r\n'
            "Content-Type: video/mp4\r\n\r\n"
        ).encode()
        + content
        + f"\r\n--{boundary}--\r\n".encode()
    )
    return body, f"multipart/form-data; boundary={boundary}"


def start(
    command: list[str], cwd: Path, env: dict[str, str], log_path: Path
) -> tuple[subprocess.Popen[bytes], TextIO]:
    log = log_path.open("w", encoding="utf-8")
    process = subprocess.Popen(
        command, cwd=cwd, env=env, stdout=log, stderr=subprocess.STDOUT
    )
    return process, log


def main(external: bool = False) -> int:
    if not external and (not MAVEN or not JAVA):
        raise RuntimeError(
            "本地验收需要 PATH 中可用的 Maven 与 Java（项目目标 JDK 17/18）。"
        )
    agent_port, media_port = (18000, 18081) if external else (free_port(), free_port())
    with tempfile.TemporaryDirectory(
        prefix="enterprise-insight-acceptance-"
    ) as temp_raw:
        temp = Path(temp_raw)
        agent_log, media_log = temp / "agent.log", temp / "media.log"

        if not external:
            subprocess.run(
                [MAVEN, "-q", "-DskipTests", "package"],
                cwd=MEDIA_DIR,
                check=True,
            )
            jar = MEDIA_DIR / "target" / "video-platform-0.0.1-SNAPSHOT.jar"
            if not jar.exists():
                raise FileNotFoundError(f"Media Service jar 未生成：{jar}")

        agent_env = os.environ.copy()
        # Keep the 192-bit random HMAC secret at exactly 32 ASCII bytes:
        # JJWT selects HS256 for this key size, matching Agent's accepted alg.
        shared_secret = secrets.token_urlsafe(24)
        service_token = secrets.token_urlsafe(32)

        agent_env.update(
            {
                "AGENT_AUTH_MODE": "jwt",
                "APP_ENV": "development",
                "SHARED_JWT_SECRET": shared_secret,
                "APP_JWT_ISSUER": "enterprise-insight",
                "APP_JWT_AUDIENCE": "enterprise-insight-api",
                "MEDIA_INGEST_SERVICE_TOKEN": service_token,
                "DEFAULT_ANSWER_MODE": "local",
                "RETRIEVER_MODE": "keyword",
                "EMBEDDING_MODEL": "",
                "RERANKER_MODEL": "",
                "AGENT_DATABASE_PATH": str(temp / "agent.sqlite3"),
            }
        )
        media_env = os.environ.copy()
        media_env.update(
            {
                "SERVER_PORT": str(media_port),
                "APP_JWT_SECRET": shared_secret,
                "APP_JWT_ISSUER": "enterprise-insight",
                "APP_JWT_AUDIENCE": "enterprise-insight-api",
                "APP_AGENT_INTEGRATION_ENABLED": "true",
                "AGENT_SERVICE_BASE_URL": f"http://127.0.0.1:{agent_port}",
                "MEDIA_INGEST_SERVICE_TOKEN": service_token,
                "APP_AGENT_DISPATCH_INTERVAL_MS": "200",
                "APP_STORAGE_BASE_PATH": str(temp / "media"),
                "APP_TRANSCRIPT_ENABLED": "false",
                "APP_SUMMARY_ENABLED": "false",
            }
        )

        processes: list[tuple[subprocess.Popen[bytes], TextIO]] = []
        try:
            if not external:
                processes.append(
                    start(
                        [
                            sys.executable,
                            "-m",
                            "uvicorn",
                            "app.main:app",
                            "--host",
                            "127.0.0.1",
                            "--port",
                            str(agent_port),
                        ],
                        AGENT_DIR,
                        agent_env,
                        agent_log,
                    )
                )
                wait_ready(
                    f"http://127.0.0.1:{agent_port}/health", processes[-1][0], agent_log
                )
                processes.append(
                    start(
                        [JAVA, "-jar", str(jar), "--spring.profiles.active=h2"],
                        MEDIA_DIR,
                        media_env,
                        media_log,
                    )
                )
                wait_ready(
                    f"http://127.0.0.1:{media_port}/actuator/health",
                    processes[-1][0],
                    media_log,
                )

            else:
                wait_ready(f"http://127.0.0.1:{agent_port}/health", None, agent_log)
                wait_ready(f"http://127.0.0.1:{media_port}/actuator/health", None, media_log)

            _, public_status = request_json(
                f"http://127.0.0.1:{agent_port}/system/status"
            )
            assert "cache" not in public_status["embedding"]
            denied_cache_status, _ = request_json_with_errors(
                f"http://127.0.0.1:{agent_port}/embeddings/status",
            )
            assert denied_cache_status == 401

            username = f"acceptance-{uuid.uuid4().hex[:10]}"
            _, auth_envelope = request_json(
                f"http://127.0.0.1:{media_port}/api/auth/register",
                method="POST",
                payload={"username": username, "password": "local-pass-123"},
            )
            auth = auth_envelope["data"]
            assert auth["tenantId"] and auth["role"] == "admin"
            assert auth["workspaceType"] == "personal"
            token = auth["token"]

            upload_body, upload_type = multipart_file(
                "file",
                "local-acceptance.mp4",
                SAMPLE_MP4 + b"local-video-acceptance-content",
            )
            _, upload_envelope = request_json(
                f"http://127.0.0.1:{media_port}/api/media/upload/file",
                method="POST",
                token=token,
                body=upload_body,
                content_type=upload_type,
            )
            task_id = upload_envelope["data"]["taskId"]

            deadline = time.monotonic() + 20
            task = None
            while time.monotonic() < deadline:
                _, task_envelope = request_json(
                    f"http://127.0.0.1:{media_port}/api/workflow/tasks/{task_id}",
                    token=token,
                )
                task = task_envelope["data"]
                if task["status"] in {"COMPLETED", "FAILED"}:
                    break
                time.sleep(0.2)
            assert task and task["status"] == "COMPLETED", task
            assert task["tenantId"] == auth["tenantId"]
            assert (
                task["transcriptSegments"]
                and task["transcriptSegments"][0]["startMs"] == 0
            )

            deadline = time.monotonic() + 15
            chat = None
            while time.monotonic() < deadline:
                _, chat = request_json(
                    f"http://127.0.0.1:{agent_port}/chat",
                    method="POST",
                    token=token,
                    payload={
                        "question": "local-acceptance.mp4 的视频内容是什么？",
                        "answer_mode": "local",
                        "retriever_mode": "keyword",
                        "workflow_mode": "standard",
                        "asset_ids": [task["videoId"]],
                    },
                )
                sources = chat.get("sources", []) if isinstance(chat, dict) else []
                if isinstance(sources, list) and any(
                    isinstance(source, dict) and source.get("source_type") == "video"
                    for source in sources
                ):
                    break
                time.sleep(0.25)
            assert chat is not None
            assert isinstance(chat, dict) and isinstance(chat.get("sources"), list), (
                chat
            )
            video_sources = [
                source
                for source in chat["sources"]
                if isinstance(source, dict) and source.get("source_type") == "video"
            ]
            assert video_sources, chat
            source = video_sources[0]
            assert source["asset_id"] == task["videoId"] and source["start_ms"] == 0

            _, embedding_status = request_json(
                f"http://127.0.0.1:{agent_port}/embeddings/status",
                token=token,
            )
            cache = embedding_status["cache"]
            assert cache["scope"] == "process"
            assert cache["chunk_snapshots"]["requests"] > 0
            assert cache["chunk_snapshots"]["requests"] == (
                cache["chunk_snapshots"]["hits"] + cache["chunk_snapshots"]["misses"]
            )

            _, analysis = request_json(
                f"http://127.0.0.1:{agent_port}/analysis/sessions",
                method="POST",
                token=token,
                payload={
                    "objective": "生成本地验收视频的需求 PRD",
                    "asset_ids": [task["videoId"]],
                },
            )
            assert (
                analysis["status"] == "WAITING_CONFIRMATION"
                and analysis["resume_token"]
            )
            assert analysis["retrieval_mode"] == "hybrid"
            assert analysis["checkpoint_version"] == 1
            assert len(analysis["evidence_snapshot_sha256"]) == 64
            frozen_revision = analysis["evidence_revision"]
            frozen_sha256 = analysis["evidence_snapshot_sha256"]
            frozen_stages = analysis["stages"][:4]
            resume_token = analysis["resume_token"]
            answer_defaults = {
                "decision_maker": "本地验收负责人",
                "acceptance_criteria": "主链路全部自动检查通过",
                "priority_rule": "阻塞主链路的问题优先",
                "evidence_scope": "仅使用本次上传视频",
                "domain_conflict": "以合规口径为准",
                "specialist_review": "由本地验收负责人复核",
            }
            answers = {
                question["question_id"]: answer_defaults[question["question_id"]]
                for question in analysis["open_questions"]
            }
            _, analysis = request_json(
                f"http://127.0.0.1:{agent_port}/analysis/sessions/{analysis['session_id']}/confirm",
                method="POST",
                token=token,
                payload={"resume_token": resume_token, "answers": answers},
            )
            assert analysis["status"] == "DRAFT_READY" and len(analysis["stages"]) == 6
            assert analysis["checkpoint_version"] == 2
            assert analysis["evidence_revision"] == frozen_revision
            assert analysis["evidence_snapshot_sha256"] == frozen_sha256
            assert analysis["stages"][:4] == frozen_stages
            stale_status, _ = request_json_with_errors(
                f"http://127.0.0.1:{agent_port}/analysis/sessions/{analysis['session_id']}/confirm",
                method="POST",
                token=token,
                payload={"resume_token": resume_token, "answers": answers},
            )
            assert stale_status == 409
            prd_evidence = analysis["prd"]["requirements"][0]["evidence"][0]
            assert (
                prd_evidence["asset_id"] == task["videoId"]
                and prd_evidence["start_ms"] == 0
            )

            _, publication = request_json(
                f"http://127.0.0.1:{agent_port}/analysis/sessions/{analysis['session_id']}/publication/request",
                method="POST",
                token=token,
            )
            assert publication["status"] == "PUBLISH_PENDING"
            assert publication["publication"]["policy"] == "OWNER_RECONFIRMATION"
            _, publication = request_json(
                f"http://127.0.0.1:{agent_port}/analysis/sessions/{analysis['session_id']}/publication/approve",
                method="POST",
                token=token,
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
                "PUBLICATION_REQUESTED",
                "PUBLICATION_APPROVED",
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
                method="POST",
                token=token,
                payload={"approved": True},
            )
            assert candidate["status"] == "APPROVED"
            assert candidate["knowledge_document_id"].startswith("knowledge-")
            assert len(candidate["knowledge_content_sha256"]) == 64
            _, knowledge_chat = request_json(
                f"http://127.0.0.1:{agent_port}/chat",
                method="POST",
                token=token,
                payload={
                    "question": "已批准业务知识有哪些？",
                    "answer_mode": "local",
                    "retriever_mode": "keyword",
                    "workflow_mode": "standard",
                    "asset_ids": [task["videoId"]],
                },
            )
            approved_sources = [
                source
                for source in knowledge_chat["sources"]
                if source.get("origin_type") == "approved_knowledge"
            ]
            assert approved_sources, knowledge_chat
            assert (
                approved_sources[0]["knowledge_candidate_id"]
                == candidate["candidate_id"]
            )
            assert (
                approved_sources[0]["content_sha256"]
                == candidate["knowledge_content_sha256"]
            )
            lifecycle_path = (
                f"http://127.0.0.1:{agent_port}/analysis/sessions/{analysis['session_id']}"
                f"/knowledge-candidates/{candidate['candidate_id']}/lifecycle-requests"
            )
            _, supersede_request = request_json(
                lifecycle_path,
                method="POST",
                token=token,
                payload={
                    "action": "SUPERSEDE",
                    "reason": "本地验收修订知识口径",
                    "replacement_statement": "本地验收替代知识：审批结果必须在 1 秒内展示。",
                    "replacement_evidence": candidate["evidence"],
                },
            )
            assert supersede_request["status"] == "PENDING"
            _, supersede_decision = request_json(
                f"{lifecycle_path}/{supersede_request['request_id']}/decision",
                method="POST",
                token=token,
                payload={"approved": True},
            )
            assert supersede_decision["status"] == "APPROVED"
            _, superseded_deliverables = request_json(
                f"http://127.0.0.1:{agent_port}/analysis/sessions/{analysis['session_id']}/deliverables",
                token=token,
            )
            assert [
                item["status"] for item in superseded_deliverables["knowledge_versions"]
            ] == [
                "SUPERSEDED",
                "ACTIVE",
            ]
            _, historical_log = request_json(
                f"http://127.0.0.1:{agent_port}/chat-logs/{knowledge_chat['log_id']}",
                token=token,
            )
            historical_knowledge = next(
                source
                for source in historical_log["sources"]
                if source.get("knowledge_candidate_id") == candidate["candidate_id"]
            )
            assert historical_knowledge["knowledge_lifecycle_status"] == "SUPERSEDED"
            _, replacement_chat = request_json(
                f"http://127.0.0.1:{agent_port}/chat",
                method="POST",
                token=token,
                payload={
                    "question": "本地验收替代知识是什么？",
                    "answer_mode": "local",
                    "retriever_mode": "keyword",
                    "workflow_mode": "standard",
                },
            )
            assert any(
                source.get("knowledge_version_number") == 2
                for source in replacement_chat["sources"]
            )
            _, revoke_request = request_json(
                lifecycle_path,
                method="POST",
                token=token,
                payload={"action": "REVOKE", "reason": "本地验收确认规则停止生效"},
            )
            _, revoke_decision = request_json(
                f"{lifecycle_path}/{revoke_request['request_id']}/decision",
                method="POST",
                token=token,
                payload={"approved": True},
            )
            assert revoke_decision["status"] == "APPROVED"
            _, revoked_chat = request_json(
                f"http://127.0.0.1:{agent_port}/chat",
                method="POST",
                token=token,
                payload={
                    "question": "本地验收替代知识是什么？",
                    "answer_mode": "local",
                    "retriever_mode": "keyword",
                    "workflow_mode": "standard",
                },
            )
            assert not any(
                source.get("knowledge_candidate_id") == candidate["candidate_id"]
                for source in revoked_chat["sources"]
            )
            action_item = deliverables["action_items"][0]
            _, ticket_draft = request_json(
                f"http://127.0.0.1:{agent_port}/analysis/sessions/{analysis['session_id']}"
                f"/action-items/{action_item['action_item_id']}/ticket-draft",
                method="POST",
                token=token,
            )
            assert ticket_draft["action_item"]["status"] == "TICKET_PENDING_APPROVAL"
            _, ticket_approval = request_json(
                f"http://127.0.0.1:{agent_port}/pending-actions/{ticket_draft['pending_action_id']}/approve",
                method="POST",
                token=token,
                payload={"approved": True},
            )
            assert ticket_approval["status"] == "succeeded"
            _, settled_deliverables = request_json(
                f"http://127.0.0.1:{agent_port}/analysis/sessions/{analysis['session_id']}/deliverables",
                token=token,
            )
            settled_action = settled_deliverables["action_items"][0]
            assert settled_action["status"] == "TICKET_CREATED"
            assert (
                settled_action["ticket_id"]
                == ticket_approval["result"]["ticket"]["ticket_id"]
            )
            _, tickets = request_json(
                f"http://127.0.0.1:{agent_port}/tickets",
                token=token,
            )
            assert tickets["total"] == 1

            _, playback_envelope = request_json(
                f"http://127.0.0.1:{media_port}/api/media/video/{task_id}/playback-token",
                token=token,
            )
            stream_url = playback_envelope["data"]["streamUrl"]
            playback_url = f"http://127.0.0.1:{media_port}{stream_url}"
            playback_status, playback_body = http_request(
                playback_url,
                headers={"Range": "bytes=0-3"},
                timeout=10,
            )
            assert playback_status == 206 and playback_body == SAMPLE_MP4[:4]

            # Team Workspace slice: one owner creates and uploads, a second
            # registered member consumes the same media/Agent resources, while
            # that member's personal workspace remains isolated.
            _, team_envelope = request_json(
                f"http://127.0.0.1:{media_port}/api/workspaces",
                method="POST",
                token=token,
                payload={"name": "Local Acceptance Team"},
            )
            team = team_envelope["data"]
            team_tenant = team["tenantId"]
            assert team["workspaceType"] == "team" and team["role"] == "OWNER"

            _, invitation_envelope = request_json(
                f"http://127.0.0.1:{media_port}/api/workspaces/{team_tenant}/invitations",
                method="POST",
                token=token,
            )
            invitation_code = invitation_envelope["data"]["invitationCode"]
            assert len(invitation_code) >= 32

            member_username = f"acceptance-member-{uuid.uuid4().hex[:10]}"
            _, member_envelope = request_json(
                f"http://127.0.0.1:{media_port}/api/auth/register",
                method="POST",
                payload={"username": member_username, "password": "local-pass-123"},
            )
            member_personal = member_envelope["data"]
            _, accepted_envelope = request_json(
                f"http://127.0.0.1:{media_port}/api/workspaces/invitations/accept",
                method="POST",
                token=member_personal["token"],
                payload={"invitationCode": invitation_code},
            )
            assert accepted_envelope["data"]["role"] == "MEMBER"

            _, owner_team_envelope = request_json(
                f"http://127.0.0.1:{media_port}/api/workspaces/{team_tenant}/switch",
                method="POST",
                token=token,
            )
            owner_team = owner_team_envelope["data"]
            _, member_team_envelope = request_json(
                f"http://127.0.0.1:{media_port}/api/workspaces/{team_tenant}/switch",
                method="POST",
                token=member_personal["token"],
            )
            member_team = member_team_envelope["data"]
            assert owner_team["role"] == "admin" and member_team["role"] == "operator"

            team_upload_body, team_upload_type = multipart_file(
                "file",
                "team-acceptance.mp4",
                SAMPLE_MP4 + b"team-video-acceptance-content",
            )
            _, team_upload_envelope = request_json(
                f"http://127.0.0.1:{media_port}/api/media/upload/file",
                method="POST",
                token=owner_team["token"],
                body=team_upload_body,
                content_type=team_upload_type,
            )
            team_task_id = team_upload_envelope["data"]["taskId"]
            team_task = None
            deadline = time.monotonic() + 20
            while time.monotonic() < deadline:
                _, team_task_envelope = request_json(
                    f"http://127.0.0.1:{media_port}/api/workflow/tasks/{team_task_id}",
                    token=member_team["token"],
                )
                team_task = team_task_envelope["data"]
                if team_task["status"] in {"COMPLETED", "FAILED"}:
                    break
                time.sleep(0.2)
            assert team_task and team_task["status"] == "COMPLETED", team_task
            assert (
                team_task["owner"] == auth["userId"]
                and team_task["tenantId"] == team_tenant
            )

            _, member_personal_tasks = request_json(
                f"http://127.0.0.1:{media_port}/api/workflow/tasks",
                token=member_personal["token"],
            )
            assert team_task_id not in {
                item["taskId"] for item in member_personal_tasks["data"]
            }

            team_chat = None
            deadline = time.monotonic() + 15
            while time.monotonic() < deadline:
                _, team_chat = request_json(
                    f"http://127.0.0.1:{agent_port}/chat",
                    method="POST",
                    token=member_team["token"],
                    payload={
                        "question": "team-acceptance.mp4 的团队视频内容是什么？",
                        "answer_mode": "local",
                        "retriever_mode": "keyword",
                        "workflow_mode": "standard",
                        "asset_ids": [team_task["videoId"]],
                    },
                )
                if any(
                    source.get("asset_id") == team_task["videoId"]
                    for source in team_chat.get("sources", [])
                ):
                    break
                time.sleep(0.25)
            assert team_chat and any(
                source.get("asset_id") == team_task["videoId"]
                for source in team_chat["sources"]
            ), team_chat

            _, team_analysis = request_json(
                f"http://127.0.0.1:{agent_port}/analysis/sessions",
                method="POST",
                token=owner_team["token"],
                payload={
                    "objective": "生成团队视频协作验收 PRD",
                    "asset_ids": [team_task["videoId"]],
                },
            )
            if team_analysis["status"] == "WAITING_CONFIRMATION":
                team_answers = {
                    question["question_id"]: answer_defaults[question["question_id"]]
                    for question in team_analysis["open_questions"]
                }
                _, team_analysis = request_json(
                    f"http://127.0.0.1:{agent_port}/analysis/sessions/{team_analysis['session_id']}/confirm",
                    method="POST",
                    token=owner_team["token"],
                    payload={
                        "resume_token": team_analysis["resume_token"],
                        "answers": team_answers,
                    },
                )
            assert team_analysis["status"] == "DRAFT_READY"
            _, team_publication = request_json(
                f"http://127.0.0.1:{agent_port}/analysis/sessions/{team_analysis['session_id']}/publication/request",
                method="POST",
                token=owner_team["token"],
            )
            approval_payload = {
                "request_id": team_publication["publication"]["request_id"],
                "approval_token": team_publication["publication"]["approval_token"],
                "confirmation": "PUBLISH",
            }
            self_status, _ = request_json_with_errors(
                f"http://127.0.0.1:{agent_port}/analysis/sessions/{team_analysis['session_id']}/publication/approve",
                method="POST",
                token=owner_team["token"],
                payload=approval_payload,
            )
            assert self_status == 403
            _, team_publication = request_json(
                f"http://127.0.0.1:{agent_port}/analysis/sessions/{team_analysis['session_id']}/publication/approve",
                method="POST",
                token=member_team["token"],
                payload=approval_payload,
            )
            assert team_publication["status"] == "PUBLISHED"
            _, team_deliverables = request_json(
                f"http://127.0.0.1:{agent_port}/analysis/sessions/{team_analysis['session_id']}/deliverables",
                token=member_team["token"],
            )
            team_candidate = team_deliverables["knowledge_candidates"][0]
            _, team_candidate = request_json(
                f"http://127.0.0.1:{agent_port}/analysis/sessions/{team_analysis['session_id']}"
                f"/knowledge-candidates/{team_candidate['candidate_id']}/decision",
                method="POST",
                token=member_team["token"],
                payload={"approved": True},
            )
            assert team_candidate["status"] == "APPROVED"
            team_lifecycle_path = (
                f"http://127.0.0.1:{agent_port}/analysis/sessions/{team_analysis['session_id']}"
                f"/knowledge-candidates/{team_candidate['candidate_id']}/lifecycle-requests"
            )
            _, team_lifecycle = request_json(
                team_lifecycle_path,
                method="POST",
                token=owner_team["token"],
                payload={
                    "action": "SUPERSEDE",
                    "reason": "团队二次评审修订",
                    "replacement_statement": "团队替代知识：协作审批必须保留审计。",
                    "replacement_evidence": team_candidate["evidence"],
                },
            )
            team_self_status, _ = request_json_with_errors(
                f"{team_lifecycle_path}/{team_lifecycle['request_id']}/decision",
                method="POST",
                token=owner_team["token"],
                payload={"approved": True},
            )
            assert team_self_status == 403
            _, team_lifecycle_decision = request_json(
                f"{team_lifecycle_path}/{team_lifecycle['request_id']}/decision",
                method="POST",
                token=member_team["token"],
                payload={"approved": True},
            )
            assert team_lifecycle_decision["status"] == "APPROVED"

            _, team_ticket_draft = request_json(
                f"http://127.0.0.1:{agent_port}/analysis/sessions/{team_analysis['session_id']}"
                f"/action-items/{team_deliverables['action_items'][0]['action_item_id']}/ticket-draft",
                method="POST",
                token=member_team["token"],
            )
            _, team_ticket_approval = request_json(
                f"http://127.0.0.1:{agent_port}/pending-actions/{team_ticket_draft['pending_action_id']}/approve",
                method="POST",
                token=owner_team["token"],
                payload={"approved": True},
            )
            assert team_ticket_approval["status"] == "succeeded"

            _, role_update = request_json(
                f"http://127.0.0.1:{media_port}/api/workspaces/{team_tenant}/members/{member_personal['userId']}",
                method="PATCH",
                token=owner_team["token"],
                payload={"role": "VIEWER"},
            )
            assert role_update["data"]["role"] == "VIEWER"
            _, viewer_session_envelope = request_json(
                f"http://127.0.0.1:{media_port}/api/workspaces/{team_tenant}/switch",
                method="POST",
                token=member_team["token"],
            )
            viewer_team = viewer_session_envelope["data"]
            assert viewer_team["role"] == "viewer"
            _, viewer_tasks = request_json(
                f"http://127.0.0.1:{media_port}/api/workflow/tasks",
                token=viewer_team["token"],
            )
            assert team_task_id in {item["taskId"] for item in viewer_tasks["data"]}
            denied_body, denied_type = multipart_file(
                "file", "viewer-denied.mp4", b"\x00\x00\x00\x18ftypisomdenied"
            )
            denied_status, _ = request_json_with_errors(
                f"http://127.0.0.1:{media_port}/api/media/upload/file",
                method="POST",
                token=viewer_team["token"],
                body=denied_body,
                content_type=denied_type,
            )
            assert denied_status == 403

            print(
                json.dumps(
                    {
                        "result": "PASS",
                        "network_scope": "localhost-only",
                        "environment": "MySQL/Redis/RocketMQ/MinIO/Keycloak/RS256; mock AI" if external else "H2/SQLite; mock AI",
                        "tenant_id": auth["tenantId"],
                        "team_tenant_id": team_tenant,
                        "task_id": task_id,
                        "team_task_id": team_task_id,
                        "asset_id": task["videoId"],
                        "video_evidence": {
                            "start_ms": source["start_ms"],
                            "end_ms": source["end_ms"],
                        },
                        "checks": [
                            "register_workspace",
                            "jwt_tenant",
                            "upload",
                            "mock_transcript",
                            "outbox_delivery",
                            "agent_retrieval",
                            "timestamp_source",
                            "analysis_wait_resume",
                            "evidence_prd",
                            "publication_approval_audit",
                            "immutable_prd_snapshot",
                            "knowledge_candidate_approval",
                            "action_item_ticket_approval",
                            "range_playback",
                            "team_invitation_and_switch",
                            "team_media_cross_member_read",
                            "personal_workspace_isolation",
                            "team_agent_retrieval",
                            "team_four_eyes_publication",
                            "team_knowledge_and_ticket_delivery",
                            "viewer_read_only",
                            "cache_metrics_auth_boundary",
                            "cache_scope_after_retrieval",
                            "approved_knowledge_materialized",
                            "approved_knowledge_retrieval",
                            "objective_evidence_snapshot",
                            "checkpoint_resume_stability",
                            "resume_token_cas",
                            "knowledge_supersede_lineage",
                            "knowledge_revoke_future_retrieval",
                            "historical_citation_status",
                            "knowledge_lifecycle_approval",
                            "team_lifecycle_four_eyes",
                        ],
                    },
                    ensure_ascii=False,
                    indent=2,
                )
            )
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
                failure_dir = (
                    Path(tempfile.gettempdir())
                    / f"enterprise-insight-failure-{int(time.time())}"
                )
                failure_dir.mkdir(parents=True, exist_ok=False)
                for source in (agent_log, media_log):
                    if source.exists():
                        shutil.copy2(source, failure_dir / source.name)
                print(
                    f"Local acceptance logs preserved at: {failure_dir}",
                    file=sys.stderr,
                )


if __name__ == "__main__":
    external = "--external" in sys.argv
    if external:
        from local_oidc import register_workspace
        original_request_json = request_json

        def request_json(url: str, **kwargs):
            if url == "http://127.0.0.1:18081/api/auth/register":
                return register_workspace(**kwargs["payload"])
            return original_request_json(url, **kwargs)

    raise SystemExit(main(external=external))
