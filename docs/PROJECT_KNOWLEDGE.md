# Project Knowledge Base

This file is the navigation entry for future Codex sessions. Read it first, then open only the referenced document needed for the task.

## Product Priority

Primary goal:

> Help real users upload videos, wait for processing, receive usable transcript/summary results, and manage their history.

Engineering work serves that goal. Large-file transfer, high concurrency, deployment, testing, and observability are important only when they improve the real user workflow.

## Current System

- Backend: Java 17, Spring Boot 3.3.5, Spring Security, JPA.
- Auth: JWT login/register with persisted users.
- Upload: single-file mode and optional Redis chunk upload.
- Workflow: local `@Async` publisher or optional RocketMQ.
- Processing: FFmpeg audio extraction, Whisper-compatible transcription, OpenAI-compatible summary, mock fallback.
- Frontend: static HTML/CSS/JS under `src/main/resources/static/`.

## Source Of Truth

> 归类说明(2026-07-02):参考类文档已移入 `docs/`;根目录仅保留 `README.md`、`CLAUDE.md`、`AGENTS.md`、`INTERVIEW_GUIDE.md`。下列相对路径以本文件(`docs/`)为基准。

- `../AGENTS.md`: project rules and coding constraints (Codex). `../CLAUDE.md` is the Claude-Code equivalent.
- `../README.md`: user-facing overview and run instructions.
- `../INTERVIEW_GUIDE.md`: 权威的功能清单 + 面试要点总结(截至当前代码).
- `CAREER_ROADMAP.md`: product direction, implementation roadmap, interview framing.
- `TROUBLESHOOTING.md`: real engineering problem cards and historical debugging notes.
- `DEMO_SCRIPT.md`: short demo flow for interview or stakeholder walkthroughs.
- `INTERVIEW_PREP.html`: deeper architecture explanation (静态,可能滞后于代码).

## Working Rules

- Preserve owner isolation for uploads and workflow tasks.
- Keep workflow state mutation transactional.
- Do not make tests depend on Redis, RocketMQ, Docker, FFmpeg, Whisper, or LLM services.
- Prefer visible user value first, then optimize the engineering bottleneck that blocks it.
- For real engineering issues, record `Symptom`, `Cause`, `Fix`, `Verify yourself`, and `Interview point`.

## Near-Term Direction

1. Confirm the core user workflow: login, upload, task status, transcript/summary, history.
2. Improve missing product feedback: failure reason, retry path, task detail, upload/processing timing.
3. Establish upload performance baseline before optimizing chunk concurrency.
4. Prepare server deployment only after the user workflow is coherent enough for real users.

## Verification

- Frontend JS syntax: `node --check src/main/resources/static/app.js`
- Full test suite: `mvn test`
- Lightweight local run:

```powershell
$env:APP_REDIS_ENABLED="false"
$env:APP_MQ_ENABLED="false"
$env:APP_TRANSCRIPT_ENABLED="false"
$env:APP_SUMMARY_ENABLED="false"
$env:SPRING_DOCKER_COMPOSE_ENABLED="false"
$env:MANAGEMENT_HEALTH_REDIS_ENABLED="false"
mvn spring-boot:run
```

- Health check: `http://localhost:8081/actuator/health`
- Frontend: `http://localhost:8081`
- Swagger: `http://localhost:8081/swagger-ui.html`

## Session Notes 2026-07-01

- Frontend now has an upload experiment panel for comparing normal upload and Redis chunk upload.
- Redis chunk upload is implemented as browser-side concurrent chunk upload with concurrency `4`.
- Upload metrics keep the latest real upload result and separate recent records for normal upload and Redis chunk upload. Switching modes must not rewrite historical metric results.
- Task history supports owner-scoped deletion through `DELETE /api/workflow/tasks/{taskId}`.
- Redis maps host port `7379` to container `6379` because this Windows environment reserves `6379-6478`.
- MySQL is available in Docker Compose behind the `mysql` profile for persistence validation.
- Important explanation: Redis chunk upload gives upload session state, chunk tracking, merge locking, and a basis for retry/resume. Upload speed improvement comes from concurrent chunks, chunk-size tuning, retries, resume, and instant-upload logic. RocketMQ improves post-upload task queueing and decoupling, not browser-to-server upload speed.
- Engineering-optimization pass: applied 5 backend/doc fixes over the code added since 2026-06-13 — see `TROUBLESHOOTING.md` → "代码优化与质量改进记录（2026-07-01）". Notable: unified `DistributedLockService.tryLock` semantics (the Redisson path used to wait and then re-run a concurrent merge, duplicating the task), stopped the HTTP 500 handler from leaking internal exception messages, cleaned up half-written files on merge failure, and corrected the stale `@Transactional` guidance in `CLAUDE.md` (the workflow now uses per-stage short transactions).

Redis validation:

```powershell
docker compose up -d redis
$env:APP_REDIS_ENABLED="true"
$env:APP_MQ_ENABLED="false"
$env:APP_TRANSCRIPT_ENABLED="false"
$env:APP_SUMMARY_ENABLED="false"
$env:SPRING_DOCKER_COMPOSE_ENABLED="false"
$env:SPRING_DATA_REDIS_PORT="7379"
mvn spring-boot:run
```

MySQL + Redis validation:

```powershell
docker compose --profile mysql up -d redis mysql
$env:MYSQL_HOST="localhost"
$env:MYSQL_PORT="3306"
$env:MYSQL_DATABASE="videoplatform"
$env:MYSQL_USERNAME="root"
$env:MYSQL_PASSWORD="123456"
$env:APP_REDIS_ENABLED="true"
$env:APP_MQ_ENABLED="false"
$env:APP_TRANSCRIPT_ENABLED="false"
$env:APP_SUMMARY_ENABLED="false"
$env:SPRING_DOCKER_COMPOSE_ENABLED="false"
$env:SPRING_DATA_REDIS_PORT="7379"
mvn spring-boot:run "-Dspring-boot.run.profiles=mysql"
```
