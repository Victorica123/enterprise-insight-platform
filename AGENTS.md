# AGENTS.md

This file provides guidance to Codex (Codex.ai/code) when working with code in this repository.

## Project Overview

**视频内容理解平台** — A Spring Boot 3 video processing platform with:
- Multi-user support (JWT authentication + database persistence)
- Chunked video uploads with Redis-backed session management
- Async video-to-text workflow (FFmpeg → Whisper → LLM summarization)
- Conditional component loading (zero-dependency to full distributed mode)

**Tech Stack**: Java 17, Spring Boot 3.3.5, Spring Security, JPA, H2/MySQL, Redis, RocketMQ, Redisson

---

## Architecture Overview

### Layered Design with Conditional Assembly

The platform uses `@ConditionalOnProperty` throughout to support three deployment modes:

1. **Pure Local** (`app.redis.enabled=false`, `app.mq.enabled=false`)
   - Single-file upload, `@Async` local processing, no distributed dependencies
   - Useful for development without Docker

2. **Default Mode** (`app.redis.enabled=true`, `app.mq.enabled=false`)  
   - Chunked upload (Redis), local `@Async` processing
   - Balance: persistence + no message queue complexity

3. **Full Distributed** (`app.redis.enabled=true`, `app.mq.enabled=true`)
   - Chunked upload (Redis), RocketMQ workflow, decoupled processing
   - Production-ready with horizontal scaling

### Request Flow: Video Upload → Processing → Status Query

```
POST /api/media/upload/init            → (Redis lock) create upload session, return uploadId
    ↓
POST /api/media/upload/chunk (×N)      → store chunks to disk, track in Redis
    ↓
POST /api/media/upload/merge           → (Redis lock) merge chunks, create VideoTask
    ↓
WorkflowPublisher.publish(taskId)      → routes to LocalWorkflowPublisher or RocketMqWorkflowPublisher
    ↓
WorkflowProcessor.processAsync         → extract audio (FFmpeg) → transcribe (Whisper/MockTranscriptService)
                                           → summarize (LLM/MockSummaryService)
                                           → persist status (JPA, @Transactional)
    ↓
GET /api/workflow/tasks                → paginated task list (owner-filtered)
GET /api/workflow/tasks/{id}           → detailed task view with transcript/summary
```

### Key Components

| Package | Purpose | Conditional? |
|---------|---------|--------------|
| `auth/` | JWT generation, user persistence (H2/MySQL) | No |
| `config/` | Properties binding, Redis/Redisson setup, Spring Security | Partial (Redis) |
| `media/` | Single vs chunked upload abstraction; storage layer | ChunkUploadService: Yes |
| `workflow/` | Task state machine, publisher/consumer pattern, distributed locking | DistributedLockService, WorkflowPublisher: Yes |
| `transcript/` | FFmpeg wrapper + Whisper HTTP client | WhisperTranscriptService: Yes |
| `summary/` | LLM HTTP client (OpenAI-compatible API) | LlmSummaryService: Yes |
| `common/` | Shared utilities (ApiResponse, exception handler, StringUtils) | No |

---

## Key Patterns & Constraints

### 1. Owner Validation Everywhere
- `ChunkUploadService.uploadChunk()` and `mergeChunks()` check `meta.get("owner")` against authenticated user
- `WorkflowController.listMyTasks()` filters by `owner = getUserId()`
- **Never expose upload/task operations across user boundaries**

### 2. Transactional Boundaries
- `@Transactional` is **required** on methods that modify JPA entities (especially `WorkflowProcessor.processAsync()`)
- The old pattern of multiple intermediate `save()` calls was **removed** in 2026-06-13 optimization — let transaction handle batch flush at method exit
- Without `@Transactional`, partial state updates can corrupt task status on exception

### 3. Error Message Truncation
- `VideoTask.errorMessage` is `@Column(columnDefinition = "TEXT")` to hold FFmpeg logs
- `WorkflowProcessor` truncates to `MAX_ERROR_MESSAGE_LENGTH = 2000` to prevent unbounded logs
- If error exceeds limit: `"... [truncated]"` suffix is added

### 4. Null-Safe Optional Patterns
- `AuthService.login()` uses `userRepository.findByUsername().orElseThrow()`
- Whisper/Summary clients check `isBlank()` (null or trimmed empty) before API calls
- When transcript is empty but valid (video with no speech), return friendly message instead of API call

### 5. Resource Cleanup
- `AudioExtractionService` **must** call `Files.deleteIfExists(output)` in all exception/timeout paths
- Without this, FFmpeg temp files accumulate in `System.getProperty("java.io.tmpdir")/video-platform/audio/`
- Check timeout **before** reading process output stream (avoid indefinite blocking)

---

## Common Development Commands

### Redis Startup Rule
- The default runtime configuration enables Redis (`app.redis.enabled=true`) and Spring Boot Docker Compose support (`spring.docker.compose.enabled=true`). Starting Spring Boot (`mvn spring-boot:run` or `start-video-service.ps1`) starts the `redis` service from `docker-compose.yml` automatically when Docker is already running.
- Do not use VS Code `runOn: folderOpen` tasks to start Redis; opening the project should not occupy a terminal.
- Tests should not depend on Redis. `VideoPlatformApplicationTests` disables Redis and Docker Compose with test properties.

### Build & Test
```bash
# Clean rebuild (resolves "class not found" issues)
mvn clean compile

# Package as JAR
mvn clean package -DskipTests

# Run tests
mvn test

# Run single test
mvn test -Dtest=VideoTaskServiceTest#testCreateTask
```

### Local Development

```bash
# Mode 1: Zero dependencies (H2 memory, no Redis/RocketMQ)
mvn spring-boot:run

# Mode 2: With Redis (default)
mvn spring-boot:run

# Mode 3: Full stack (Redis + RocketMQ)
docker-compose up -d
mvn spring-boot:run -Dspring-boot.run.profiles=mysql,redis
```

### Database & Docker
```bash
# Start only Redis
docker compose up -d redis

# Start Redis + RocketMQ (via profiles)
docker-compose up --profile mq -d

# Tail logs (RocketMQ broker)
docker-compose logs -f rocketmq-broker

# Clean up
docker-compose down
```

### Quick Verification
```bash
# Check service is up
curl http://localhost:8080/actuator/health

# Access frontend
open http://localhost:8080
```

---

## Configuration (application.yml)

Key feature flags controlled by Spring properties:

```yaml
app:
  redis:
    enabled: true           # Enable Redis for chunked upload sessions & locks
  mq:
    enabled: false          # Enable RocketMQ for decoupled workflow processing
  transcript:
    enabled: true
    whisper:
      api-base-url: "https://api.siliconflow.cn/v1"
      api-key: "${SILICONFLOW_API_KEY}"
      model: "SenseVoiceSmall"
  summary:
    enabled: true
    llm:
      api-base-url: "https://api.deepseek.com"
      api-key: "${DEEPSEEK_API_KEY}"
      model: "deepseek-chat"

spring:
  datasource:
    url: jdbc:h2:mem:videoplatform;DB_CLOSE_DELAY=-1;DB_CLOSE_ON_EXIT=FALSE
  jpa:
    hibernate:
      ddl-auto: create-drop
```

**Profiles** (use `-Dspring-boot.run.profiles=mysql` to switch):
- `default`: H2 in-memory (data cleared on restart)
- `mysql`: External MySQL (requires `MYSQL_HOST`, `MYSQL_USER`, `MYSQL_PASSWORD` env vars)

---

## Recent Optimizations (2026-06-13)

See `docs/TROUBLESHOOTING.md` → "代码优化与质量改进记录（2026-06-13）" for full details.

**Critical fixes**:
1. **WorkflowProcessor**: Removed 4 redundant DB writes per video (now 1 per @Transactional exit)
2. **AudioExtractionService**: Fixed stream read ordering + added temp file cleanup
3. **MediaController**: Extracted repeated service-availability checks

**Code quality**:
1. Created `StringUtils` to consolidate `isBlank()` and `trimTrailingSlash()` duplication
2. Extracted `MAX_ERROR_MESSAGE_LENGTH` constant

These changes are production-ready and backward compatible.

---

## Testing & Debugging

### Common Failure Modes & Fixes

| Symptom | Root Cause | Fix |
|---------|-----------|-----|
| `Class not found: AppProperties$Transcript` | Stale `.class` files from incremental compile | `mvn clean compile` |
| 503 Service Unavailable on upload | `app.redis.enabled=false` or Redis not running | Check `application.yml`; run `docker-compose up -d redis` |
| Task stuck in `QUEUED` | Exception in async processor rolled back transaction | Check logs; inspect `VideoTask.errorMessage` in DB |
| 403 Forbidden after restart | Old JWT token in localStorage, user data cleared | F12 → Console → `localStorage.clear(); location.reload()` |
| FFmpeg timeout / temp files accumulate | `AudioExtractionService` not cleaning up on exception | Fixed in 2026-06-13 optimization; verify `MAX_ERROR_MESSAGE_LENGTH` truncation |

### Debugging Tips

- **Enable request/response logging**: Add `logging.level.org.springframework.web=DEBUG` to `application.yml`
- **Check async execution**: Search logs for `thread=task-` to confirm `@Async` methods ran
- **Inspect Redis state**: Use `redis-cli KEYS "upload:*"` to see active upload sessions
- **Watch task progression**: Query DB directly: `SELECT id, status, errorMessage FROM video_task WHERE owner = 'user123'`
- **FFmpeg errors**: Raw stderr output truncated to 2000 chars in `VideoTask.errorMessage`; full logs go to service logs

---

## File Organization

**Source root**: `src/main/java/com/example/videoplatform/`

```
├── auth/               # JWT, user accounts (JPA entities + repos)
├── common/             # ApiResponse, GlobalExceptionHandler, StringUtils
├── config/             # AppProperties, SecurityConfig, Redis/Redisson setup
├── crawl/              # (Experimental) video metadata crawler
├── media/              # Upload controllers, ChunkUploadService, MediaFileValidator
├── summary/            # LLM HTTP client (OpenAI-compatible), MockSummaryService
├── transcript/         # FFmpeg wrapper, Whisper HTTP client, MockTranscriptService
├── workflow/           # Task state machine (VideoTask entity), WorkflowProcessor,
                        # WorkflowPublisher abstraction, RocketMQ consumer/producer
└── VideoPlatformApplication.java
```

**Resources**:
```
src/main/resources/
├── application.yml     # Default config (H2 + local @Async)
├── application-mysql.yml
├── application-redis.yml
└── static/             # Frontend: index.html, app.js, app.css
```

---

## When to Use What

**Modifying VideoTask status flow?**
- Always wrap in `@Transactional` method
- Call `videoTaskService.save(task)` once at the end (not after each field assignment)
- Handle exceptions to persist FAILED status

**Adding a new external API client?**
- Follow `OpenAiCompatibleWhisperClient` or `OpenAiCompatibleSummaryClient` pattern
- Extract timeouts as `private static final Duration` fields
- Use `StringUtils.isBlank()` and `StringUtils.trimTrailingSlash()`
- Add `@ConditionalOnProperty` if feature is optional

**Fixing upload bugs?**
- Check `ChunkUploadService.requireUploadOwner()` — may be auth issue
- Verify Redis expiration (`redisTemplate.expire(key, Duration.ofHours(24))`) is set
- Confirm `MediaFileValidator.safeVideoFileName()` is called for all user-provided names

**Scaling for production?**
- Switch to MySQL profile: `application-mysql.yml`
- Enable RocketMQ: `app.mq.enabled=true` in `docker-compose`
- Use Redisson for distributed locking (already configured in `RedissonClientConfig`)
- Consider thread pool tuning in `AsyncConfig` if async task throughput becomes a bottleneck

---

## Documentation References

- **Detailed troubleshooting & past issues**: `docs/TROUBLESHOOTING.md`
- **Interview-ready architecture explanation**: `docs/INTERVIEW_PREP.html` (deep dive); `INTERVIEW_GUIDE.md` (current features + interview points, authoritative)
- **Project launch script**: `start-video-service.ps1` (Windows PowerShell)
- **README.md**: Feature overview, quick-start guide, tech stack

---

## Notes for Next Codex Session

- This codebase has **strong ownership constraints** — every upload/task must be tied to an authenticated user
- The platform was refactored from single-user to multi-user in May 2026; keep user context in mind when reviewing old PRs
- Recent 2026-06-13 optimizations removed redundant DB operations; if you see `videoTaskService.save()` called multiple times in workflow, it's likely a regression
- FFmpeg failures are common with unsupported video formats; graceful degradation (empty transcript → friendly summary) is the pattern
- Redis/RocketMQ are optional but heavily tested — prefer conditional components over removing them entirely
