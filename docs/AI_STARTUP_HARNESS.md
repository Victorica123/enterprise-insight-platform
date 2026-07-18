# AI Startup Harness

Purpose: give Codex/Claude a small, stable startup context and avoid rereading long docs every turn.

## Project In One Screen

Video content understanding platform, Java 17 + Spring Boot 3.3.5.

Core user flow:

1. User logs in with JWT.
2. User uploads video by one of three paths:
   - normal multipart upload;
   - Redis chunk upload with resume/merge;
   - S3/MinIO direct upload via presigned PUT, then complete callback.
3. Backend creates `VideoTask`.
4. `WorkflowPublisher` dispatches locally or through RocketMQ.
5. `WorkflowProcessor` extracts audio, transcribes, summarizes, and updates task state.
6. User views task history, transcript, summary, retry/delete actions, and playback.

## Current Priority

Primary goal: help real users upload videos, wait for processing, receive transcript/summary, play videos, and manage history.

Engineering topics such as Redis, RocketMQ, object storage, load tests, and observability exist to support that user flow.

## Current Architecture Flags

- `app.redis.enabled=false`, `app.mq.enabled=false`: H2/local lightweight mode.
- `app.redis.enabled=true`, `app.mq.enabled=false`: Redis chunk upload + local async processing.
- `app.redis.enabled=true`, `app.mq.enabled=true`: Redis + RocketMQ distributed workflow.
- `app.storage.type=local`: default disk storage.
- `app.storage.type=s3`: MinIO/S3-compatible storage, playback redirect, direct upload backend.

## Recent State Snapshot

- P2 MQ A/B validation exists in `docs/LOADTEST.md` and `loadtest/results/RESULTS.md`.
- P3 reliability exists: stale-task reaper, manual failed-task retry, `video.task.requeued` metrics.
- P4 storage exists: `MediaStorageService`, local/S3 implementations, MinIO compose profile, playback 307 redirect, direct-upload UI/API.
- Direct upload uses `init / browser PUT / complete`; MinIO CORS is configured for local frontend, and repeated `complete` returns the existing task for the same owner/storagePath.
- P5 small-scale deployment now exists: `Dockerfile`, `.env.example`, `docker-compose.prod.yml`, `observability/prometheus.prod.yml`, `scripts/verify-deploy.ps1`, and `docs/P5_SMALL_SCALE_DEPLOYMENT.md`.
- P5 public-entry hardening now includes Compose-managed Caddy automatic HTTPS, public blocking for metrics/Swagger, container log rotation, app/Redis health checks, `scripts/preflight-deploy.ps1`, and the Chinese beginner guide `docs/P5_BEGINNER_LAUNCH_GUIDE.md`.
- S3 direct upload has separate internal and browser-visible endpoints: `APP_STORAGE_S3_ENDPOINT` for the app container and `APP_STORAGE_S3_PUBLIC_ENDPOINT` for presigned browser URLs.
- Full-stack verification script exists: `scripts/verify-full-stack.ps1`.
- Feature-to-evidence map exists: `docs/VERIFICATION_MATRIX.md`.
- Frontend result delivery supports copying transcript/summary and downloading Markdown notes.
- Local async lab exists: `scripts/start-async-lab.ps1` + page A/B panel compare real local `@Async` and RocketMQ without public hosting.
- Per-user active-task admission control uses a locked user row; full capacity returns 429 and is visible as `处理中 x/y`.
- MQ consumer concurrency is explicit (`APP_MQ_CONSUMER_THREADS`, default 4) so fair A/B does not confuse more workers with MQ acceleration.
- Latest verification: full suite baseline is 79 tests; JS syntax, async-lab PowerShell parse, production Compose config, desktop/mobile browser smoke, real local overload and real RocketMQ runs passed. H2 integration proves 10 concurrent creates cannot exceed a per-owner limit of 3.

## High-Value Rules

- Owner isolation is mandatory on uploads, playback, workflow tasks, retries, and deletes.
- Never make unit tests depend on Redis, RocketMQ, Docker, FFmpeg, Whisper, or LLM APIs.
- MQ does not speed up a single task; it converts visible request failure into internal queueing delay.
- Consumer concurrency can raise throughput, but that is additional worker capacity rather than the queue making work cheaper.
- Redis chunk upload helps resume, merge locking, chunk tracking, and later upload optimization; it does not automatically make a single upload faster.
- Object storage/direct upload reduces application-server bandwidth and disk pressure; it does not make transcription faster.
- Keep workflow state changes in short transactions through `VideoTaskService`.
- Do not revert existing uncommitted changes unless the user explicitly asks.

## Topic Routing

Open only what the current task needs:

- Need latest cross-model state: `docs/AI_HANDOFF.md`
- Need roadmap/user value: `docs/PROJECT_KNOWLEDGE.md`, `docs/CAREER_ROADMAP.md`
- Need MQ/performance result: `docs/LOADTEST.md`, `loadtest/results/RESULTS.md`
- Need page-driven local async verification: `docs/ASYNC_LAB.md`
- Need reliability/retry: `docs/P3_RELIABILITY_VERIFICATION.md`
- Need object storage/direct upload: `docs/P4_OBJECT_STORAGE.md`
- Need small-scale deployment/debug: `docs/P5_SMALL_SCALE_DEPLOYMENT.md`
- Need step-by-step first launch: `docs/P5_BEGINNER_LAUNCH_GUIDE.md`
- Need real bug history: `docs/TROUBLESHOOTING.md`
- Need proof for a capability: `docs/VERIFICATION_MATRIX.md`
- Need interview phrasing: `INTERVIEW_GUIDE.md`

## Verification Ladder

- Frontend JS only: `node --check src/main/resources/static/app.js`
- Narrow media/API work: `mvn test "-Dtest=MediaControllerTests,DirectUploadServiceTests,VideoPlaybackControllerTests"`
- Workflow work: `mvn test "-Dtest=WorkflowControllerTests,WorkflowProcessorTests,VideoTaskServiceTests"`
- Broad backend change: `mvn test`
- Real Redis/MySQL/RocketMQ chain: `powershell -NoProfile -ExecutionPolicy Bypass -File scripts\verify-full-stack.ps1`
