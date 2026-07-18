# AI Handoff

This is the shared handoff entrypoint for Codex, Claude, and future AI agents working on this repository.
Read this after AGENTS.md or CLAUDE.md, then open only the referenced docs needed for the current task.

Token-saving startup rule: AGENTS.md and CLAUDE.md are now short harness pointers. First read `docs/AI_STARTUP_HARNESS.md`; read this file only when recent cross-model state is needed; open topic docs lazily.

## Current Product Goal

Help real users upload videos, wait for processing, receive transcript/summary results, play back videos when needed, and manage their history. Performance, MQ, Redis, observability, and deployment work should serve that user workflow.

## Canonical Context

- docs/PROJECT_KNOWLEDGE.md - navigation map and current product priorities.
- docs/AI_STARTUP_HARNESS.md - compact startup cache/harness for future agents.
- docs/P5_SMALL_SCALE_DEPLOYMENT.md - small-scale single-server deployment, smoke verification, and debug playbook.
- docs/P5_BEGINNER_LAUNCH_GUIDE.md - step-by-step Chinese guide for the first public trial.
- CLAUDE.md - short Claude startup harness and load-order rules.
- AGENTS.md - Codex working rules. Keep it aligned with CLAUDE.md when architecture changes.
- docs/TROUBLESHOOTING.md - real engineering problem cards. Add new issues with Symptom, Cause, Fix, Verify yourself, and Interview point.
- docs/LOADTEST.md - MQ on/off A/B load-test method and measured results.
- docs/ASYNC_LAB.md - local page-driven async/MQ A/B without public hosting.
- docs/VERIFICATION_MATRIX.md - feature-to-evidence map and claim boundaries.
- docs/DEMO_SCRIPT.md - current 5-10 minute presentation flow.
- INTERVIEW_GUIDE.md - interview-facing feature and architecture summary.

## Shared Rules

- Treat existing uncommitted changes as user-owned unless you made them.
- Preserve owner isolation on upload, playback, crawl, and workflow records.
- Keep tests independent from Redis, RocketMQ, Docker, FFmpeg, Whisper, and LLM APIs.
- Prefer small, verifiable progress over broad rewrites.
- When a task changes architecture, update both the code and this handoff entrypoint.
- For user-facing failure modes, prefer precise 4xx errors for client-correctable problems and generic 5xx for internal faults.

## Quick State

- Generated at: 2026-07-18 +08:00
- Last agent: Codex
- Branch: main
- Last commit before current work: `70f9b11 feat: complete interview presentation package`
- Repository state: local async-lab and task-admission work is being finalized. Local `.claude/settings.json` changes remain user-owned and must stay out of commits.

## Latest Session Summary

2026-07-18 local async-lab update (Codex): added a page experiment that submits real small uploads and tracks HTTP accepted/rejected, backend tasks, active and completed states across app restarts. Added `scripts/start-async-lab.ps1 -Mode local|mq`, per-user active-task quota with locked owner row and HTTP 429, explicit MQ consumer concurrency, and a precise 503 overload handler without repeated stack traces. Real equal-worker run (80 tasks, 16 KB, 500 ms Mock, 4 workers): local accepted 54/rejected 26 and recovered all 80 in 18.55s; MQ accepted 80/rejected 0 and completed all in 11.32s.

2026-07-18 presentation update (Codex): rebuilt the GitHub README around the business flow, architecture, evidence and honest limitations; added `docs/VERIFICATION_MATRIX.md`; added frontend copy and Markdown result export; rewrote `docs/DEMO_SCRIPT.md` into a 5-10 minute current demo; and replaced the stale interview guide with current Redis/MQ/MinIO/reliability/deployment knowledge and measured MQ conclusions.

Expanded P3 verification and continued P4. P3 now has docs/P3_RELIABILITY_VERIFICATION.md with user-verifiable stale-task requeue steps and high-concurrency failure-mode explanations. P4 added MediaStorageService abstraction, LocalMediaStorageService as default, S3MediaStorageService for MinIO/S3-compatible storage without extra Maven dependencies, object-storage MinIO compose profile, playback 307 redirect to presigned object URL, and docs/P4_OBJECT_STORAGE.md.

2026-07-03 update: added owner-scoped manual retry for failed workflow tasks via `POST /api/workflow/tasks/{taskId}/retry`, requeue metrics (`video.task.requeued`, `source=reaper|manual`), frontend failed-task retry button, and a right-side engineering verification panel explaining MQ/P3/P4/retry in plain language.

2026-07-03 full-stack update: verified real Docker Redis + MySQL + RocketMQ with `scripts/verify-full-stack.ps1`. The script registers a user, performs Redis chunk init/status/chunk/merge, waits for RocketMQ workflow completion, checks MySQL persistence, and confirms Redis upload keys are cleaned. Also fixed RocketMQ consumer backpressure by calling `WorkflowProcessor.process(...)` synchronously instead of `processAsync(...)`; MQ mode should not enqueue again into the local `videoTaskExecutor`.

2026-07-03 MQ A/B recheck: after the consumer backpressure fix, ran a short k6 comparison with real Redis/MySQL/RocketMQ and mock transcript delay 2s. MQ off accepted only 140/1365 checks (10.25%, HTTP failures 89.61%) because local async saturated; MQ on accepted 1399/1399 checks (100%, HTTP failures 0%). DB showed MQ on moved the surplus into QUEUED/TRANSCRIBING tasks instead of speeding processing. Raw files: `loadtest/results/k6-short-mqoff.txt`, `loadtest/results/k6-short-mqon.txt`; summary appended to `loadtest/results/RESULTS.md`.

2026-07-03 direct upload update: added backend S3/MinIO direct-upload flow. New endpoints: `POST /api/media/upload/direct/init` returns a presigned PUT URL, storagePath, and short uploadToken; `POST /api/media/upload/direct/complete` validates token owner/purpose, checks object existence, creates a `VideoTask`, and publishes workflow. Token is bound to owner/fileName/storagePath. Local storage explicitly rejects direct upload. Docs updated in `docs/P4_OBJECT_STORAGE.md`.

2026-07-03 startup harness update: compressed root `AGENTS.md` and `CLAUDE.md` into short load-order files and added `docs/AI_STARTUP_HARNESS.md` as the always-read compact context cache. Goal is lower token use and faster context hits for Codex/Claude.

2026-07-04 direct upload UI/state update: frontend now has an "对象存储直传" upload strategy wired to `init / browser PUT / complete`, using XHR for upload progress. Added MinIO local CORS env (`MINIO_API_CORS_ALLOW_ORIGIN=http://localhost:8081,http://127.0.0.1:8081`), direct-init now returns 503 when storage does not support direct upload, and repeated `complete` for the same owner/storagePath returns the existing task without publishing workflow again.

2026-07-04 P5 small-scale deployment update: added `Dockerfile`, `.dockerignore`, `.env.example`, `docker-compose.prod.yml`, `observability/prometheus.prod.yml`, `scripts/verify-deploy.ps1`, and `docs/P5_SMALL_SCALE_DEPLOYMENT.md`. Deployment design is a controlled single-server stack: app public through reverse proxy, MySQL/Redis/RocketMQ private, MinIO API localhost-bound for reverse proxy, Grafana/Prometheus localhost-bound. S3 direct upload now supports `APP_STORAGE_S3_PUBLIC_ENDPOINT` so browser presigned URLs can use the public object-storage domain while the app container keeps using internal `APP_STORAGE_S3_ENDPOINT`.

2026-07-05 P0 deploy hardening (Claude): verified the production Docker image actually builds and boots, and closed the MinIO/S3 credential-drift trap. (1) Docker Hub base-image pulls time out on this network; pulled `eclipse-temurin:17-jre` and `maven:3.9.9-eclipse-temurin-17` via CN mirrors (DaoCloud / 1ms.run) and `docker tag`-ed them back to the original names so the Dockerfile stays registry-neutral. (2) Added `.mvn/settings-docker.xml` (Aliyun Central mirror) plus one COPY line in the Dockerfile build stage — `mvn dependency:go-offline` dropped from >10min (never finished) to 132s, `package` 25s, image built (1.31GB). (3) Isolated boot check with the `h2` profile reached `Started VideoPlatformApplication` + Tomcat 8081; `/actuator/health` returns UP once the Redis health probe is disabled. (4) Removed `MINIO_ROOT_USER`/`MINIO_ROOT_PASSWORD` from `.env.example`; `docker-compose.prod.yml` now feeds `APP_STORAGE_S3_ACCESS_KEY`/`APP_STORAGE_S3_SECRET_KEY` straight into MinIO, so the app and MinIO credentials can never mismatch (was: two independent CHANGE_ME pairs a user could set differently, causing 403 SignatureDoesNotMatch on every upload).

2026-07-16 P5 beginner launch update (Codex): added Compose-managed Caddy with automatic HTTPS for separate app/files domains, blocked public Actuator metrics and Swagger while preserving `/actuator/health`, added Docker JSON log rotation and app/Redis health checks, added `scripts/preflight-deploy.ps1`, and added `docs/P5_BEGINNER_LAUNCH_GUIDE.md`. Current non-code blocker: no Git remote is configured and roughly 57 working-tree entries remain uncommitted; prepare/review a real commit and push to a private GitHub/Gitee repository before server deployment.

## Verification

2026-07-18 async-lab verification: full-suite baseline is 79 tests; `node --check`, PowerShell parse, production Compose config and `git diff --check` passed. H2 integration proved 10 concurrent creates with an owner limit of 3 create exactly 3 tasks. Browser desktop/mobile smoke had no horizontal overflow. Real equal-worker run (80 tasks, 16 KB, Mock 500 ms, 4 workers): local accepted 54/rejected 26 and reaper recovered all 80 in 18.55s; RocketMQ accepted 80/rejected 0 and completed all in 11.32s. MQ consumer logs showed exactly four concurrent consumer threads after explicit configuration.

node --check src/main/resources/static/app.js passed. Focused tests for upload/playback/workflow previously passed: 31 tests. Full mvn test previously passed: 56 tests.

2026-07-03 verification: node --check src/main/resources/static/app.js passed; focused workflow tests (`WorkflowControllerTests,VideoTaskServiceTests,StaleWorkflowTaskReaperTests`) passed with 13 tests; full `mvn test` passed with 60 tests.

2026-07-03 full-stack verification: `scripts/verify-full-stack.ps1` passed with `ok=true`, task `COMPLETED`, transcript/summary present, MySQL row matched, Redis upload keys after merge `0`; full `mvn test` passed with 61 tests.

2026-07-03 latest verification after direct upload + harness: `mvn test` passed with 66 tests, 0 failures, 0 errors.

2026-07-04 focused verification after direct-upload UI/idempotency/CORS: `node --check src/main/resources/static/app.js` passed; `mvn test "-Dtest=MediaControllerTests,DirectUploadServiceTests,VideoPlaybackControllerTests"` passed with 16 tests.

2026-07-04 P5 verification: `mvn test "-Dtest=S3MediaStorageServiceTests,DirectUploadServiceTests"` passed with 7 tests; full `mvn test` passed with 70 tests; `docker compose -f docker-compose.prod.yml --env-file .env.example config --quiet` passed; `scripts/verify-deploy.ps1` parsed successfully; `mvn package -DskipTests` passed. Docker image build was not fully verified because Docker Hub base-image pulls timed out locally (`maven:3.9.9-eclipse-temurin-17`, `eclipse-temurin:17-jre`); treat as registry/network setup, not app compile failure.

2026-07-16 P5 verification: full `mvn test` passed with 70 tests; production Compose config passed with `.env.example`; `scripts/preflight-deploy.ps1` and `scripts/verify-deploy.ps1` parsed successfully; `git diff --check` passed. Preflight was exercised against `.env.example` and correctly rejected template values plus the stopped Docker daemon. Caddy's in-container `caddy validate` could not run because Docker Desktop was not running; rerun preflight/container validation once Docker is available or on the target server.

2026-07-05 P0 build verification (Claude): full `mvn test` still 70/70. Production image built end-to-end via CN mirrors: `go-offline` 132s + `package` 25s -> `video-platform:local` (1.31GB). Isolated `h2` container booted in ~6s to `/actuator/health` = UP (with `MANAGEMENT_HEALTH_REDIS_ENABLED=false`) and `GET /` = 200. `docker compose -f docker-compose.prod.yml --env-file .env.example config` still valid; resolved MinIO root creds now equal the S3 access/secret keys.

## Known Risks / Watch Items

S3MediaStorageService is a lightweight JDK HttpClient + Signature V4 implementation for MinIO/S3 compatibility; production can later swap in official SDK if dependency policy allows. Direct-upload UI/API exists and repeated complete is guarded by owner/storagePath. Direct upload has separate internal/public endpoints; keep them aligned with reverse proxy domains. There is still no dedicated upload-session table; add one later for audit, expiry, and cleanup.

When `APP_REDIS_ENABLED=false` (lightweight mode) the Spring Boot Redis health indicator still activates and drives `/actuator/health` to DOWN, which would make Nginx/compose health probes and `verify-deploy.ps1` treat the app as down even though it started fine. The prod compose defaults to Redis on, so the default deployment path is unaffected; if you ever deploy with Redis off, also set `MANAGEMENT_HEALTH_REDIS_ENABLED=false`. Consider coupling the two flags in config so they cannot drift.

## Recommended Next Step

Use the current package as a repeatable local engineering lab and interview demo. Public hosting is optional. Next product-hardening candidates are upload-session lifecycle/audit and safe media cleanup; database migrations and backup/CI matter only if deployment becomes a goal again.

## Handoff Log

- 2026-07-18 Codex: added local async lab, per-user active-task admission, explicit MQ consumer concurrency, 503 overload semantics, 78-test baseline, real local/MQ A/B, and docs. Public deployment is optional; local reproducibility is the default demonstration path.
- 2026-07-18 Codex: refreshed README/demo/interview/evidence docs and added user-visible result export. `node --check`, full `mvn test` (70/70), `git diff --check`, and desktop/mobile browser smoke passed; mobile had no horizontal overflow and result actions kept stable disabled states before a result exists.
