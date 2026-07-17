# CLAUDE.md

Claude startup harness for this repository. Keep this file short to reduce token use; detailed context lives in `docs/`.

## Load Order

1. Read `docs/AI_STARTUP_HARNESS.md`.
2. Read `docs/AI_HANDOFF.md` only when continuing project work or checking recent state.
3. Open topic docs only when needed:
   - Product map: `docs/PROJECT_KNOWLEDGE.md`
   - MQ/load tests: `docs/LOADTEST.md`
   - Reliability/retry: `docs/P3_RELIABILITY_VERIFICATION.md`
   - Object storage/direct upload: `docs/P4_OBJECT_STORAGE.md`
   - Small-scale deployment: `docs/P5_SMALL_SCALE_DEPLOYMENT.md`
   - Beginner launch guide: `docs/P5_BEGINNER_LAUNCH_GUIDE.md`
   - Troubleshooting history: `docs/TROUBLESHOOTING.md`
   - Feature evidence: `docs/VERIFICATION_MATRIX.md`
   - Interview framing: `INTERVIEW_GUIDE.md`

## Non-Negotiables

- Preserve owner isolation: users can only access their own uploads, playback tokens, and workflow tasks.
- Keep tests independent from Redis, RocketMQ, Docker, FFmpeg, Whisper, and LLM APIs.
- Prefer conditional components over removing Redis, RocketMQ, storage, Whisper, or LLM paths.
- Treat existing uncommitted changes as user-owned unless you made them.
- Use small, verifiable changes; run focused tests first, then `mvn test` for broad backend changes.

## Quick Commands

```powershell
mvn test
mvn test "-Dtest=MediaControllerTests,DirectUploadServiceTests"
mvn spring-boot:run -Dspring-boot.run.profiles=h2
powershell -NoProfile -ExecutionPolicy Bypass -File scripts\verify-full-stack.ps1
```
