# CLAUDE.md

Claude startup harness for this repository. Keep this file short; detailed context lives in `docs/`.

## Load Order

1. Open topic docs only when needed:
   - 参数依据/实测数据/业务落地/指标口径: `docs/PERFORMANCE.md`
   - 部署、验证与排障: `docs/OPERATIONS.md`
   - 面试框架: `INTERVIEW_GUIDE.md`
   - 演示脚本: `docs/DEMO_SCRIPT.md`

## Non-Negotiables

- Preserve owner isolation: users can only access their own uploads, playback tokens, and workflow tasks.
- Keep tests independent from Redis, RocketMQ, Docker, FFmpeg, Whisper, and LLM APIs.
- Prefer conditional components over removing Redis, RocketMQ, storage, Whisper, or LLM paths.
- 测试认证必须与生产同源：涉及身份/认证的回归用 `RealJwtUploadFlowTests` 模式（真实注册→真实 JWT→真实过滤器），不要只依赖 `.with(user(...))` 模拟。
- Use small, verifiable changes; run focused tests first, then `mvn test` for broad backend changes.

## Quick Commands

```powershell
mvn test   # JDK 17/18；JDK 25 与 Mockito inline 不兼容
mvn spring-boot:run "-Dspring-boot.run.profiles=h2"
powershell -NoProfile -ExecutionPolicy Bypass -File scripts\verify-full-stack.ps1
```
