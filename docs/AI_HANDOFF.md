# AI Handoff

Codex、Claude 和其他模型的跨会话交接入口。启动时先读 `../AGENTS.md` 或 `../CLAUDE.md`，再读 `AI_STARTUP_HARNESS.md`；只有继续开发或确认最新证据时才读本文件。

## 当前方向

项目定位为：

> 可在本地完整复现的视频内容平台和后端工程实验室。

主目标是让用户完成登录、上传、异步处理、查看转写/摘要、播放、重试和删除。Redis、RocketMQ、MySQL、MinIO、高并发实验与可观测性用于证明真实工程能力，不要求购买服务器，也不虚构线上流量、用户数、SLA 或营收。

公网部署能力已经实现并保留，但不是当前路线的前置条件。

## 当前架构

- Java 17、Spring Boot 3.3.5、Spring Security、JWT、JPA。
- 普通 multipart、Redis 分片续传、MinIO/S3 预签名直传三条上传路径。
- H2 轻量模式，以及 Redis + MySQL + RocketMQ + MinIO 完整本地模式。
- 本地 `@Async` 或 RocketMQ 分发，`WorkflowProcessor` 执行 FFmpeg、Whisper 兼容转写和 OpenAI 兼容摘要。
- `VideoTaskService` 用短事务推进状态；MQ 重投通过幂等占位避免重复处理。
- 前端可观察任务状态、上传方式、异步模式、结果、播放、重试、删除和 Markdown 导出。
- 每用户活动任务配额使用用户行悲观锁保证并发下限额准确；满额返回 429。
- 失败任务支持手动重试；卡住任务由 reaper 补偿并记录指标。

## 最新可信证据

- 当前提交基线：`a9f1ecd feat: add local async verification lab`，已推送到 `origin/main`。
- 自动化测试基线：79 个测试通过。
- H2 并发集成测试：同一用户并发创建 10 个任务、上限 3，只创建 3 个。
- 完整栈脚本已真实跑通 Redis 分片上传、RocketMQ 消费、MySQL 持久化和 Redis 会话清理。
- MinIO 直传已验证 `init -> browser PUT -> complete`、完成回调幂等和预签名播放。
- Range 播放、内容 MD5 校验、秒传、断点续传、令牌与 owner 隔离均有测试或运行证据。
- 等 worker A/B：80 请求、16 KB、Mock 500 ms、4 worker。
  - 本地 `@Async`：HTTP 接收 54/80，拒绝 26/80；reaper 最终完成 80/80，18.55 秒。
  - RocketMQ：HTTP 接收 80/80，拒绝 0；完成 80/80，11.32 秒。
  - 正确结论：MQ 改变积压和拒绝方式，不降低单任务计算成本；worker 数增加才会提高处理吞吐。

详细证据见 `VERIFICATION_MATRIX.md`、`LOADTEST.md`、`ASYNC_LAB.md` 和 `loadtest/results/RESULTS.md`。

## 不可破坏的约束

- 所有上传、播放令牌、任务、重试和删除操作必须按 owner 隔离。
- 单元/集成测试不得依赖 Docker、Redis、RocketMQ、FFmpeg、Whisper 或外部 LLM。
- 不删除 Redis、MQ、对象存储、Whisper、LLM 路径；用配置开关保持轻量模式可运行。
- FFmpeg、网络和 AI I/O 不得放进长数据库事务；异常路径不得遗留临时文件。
- 用户可修正的问题返回明确 4xx；资源饱和返回明确 429/503；内部错误才返回通用 5xx。
- 工作区已有未提交变更默认属于用户；当前 `.claude/settings*.json` 不得提交或回退。
- 文档不得把历史压测数据描述成当前生产能力。

## 已知边界

- 真实 AI 效果、费用与限流取决于用户配置的 Whisper/LLM 服务；默认 Mock 只验证工作流。
- S3 实现是基于 JDK HttpClient 的轻量 SigV4 客户端，主要验证 MinIO/S3 协议链路。
- 直传还没有独立 upload-session 表，审计、过期和孤儿对象清理仍不完整。
- 视频删除、任务删除、失败处理和对象存储之间还需要统一的媒体生命周期策略。
- Redis 关闭时需同时关闭 Spring Redis health indicator，否则健康检查可能误报 DOWN。
- 没有真实公网用户、生产 SLA、备份恢复演练或长期容量数据。

## 推荐下一步

1. **媒体生命周期清理**：明确任务删除、处理失败、用户取消时，本地文件、MinIO 对象和临时文件的删除规则；补 owner 隔离与幂等测试。
2. **上传会话治理**：增加可审计的上传会话、过期状态和孤儿分片/对象清理，保留 Redis 作为热状态。
3. **验证入口收敛**：把轻量演示、完整栈检查、异步 A/B 和 MinIO 验证整理成统一的新手入口和明确输出。
4. **可选真实 AI 验证**：只在有可控 API 配额时增加一次短视频 smoke，记录耗时与失败原因，不纳入默认测试。

## 验证命令

```powershell
node --check src/main/resources/static/app.js
mvn test
powershell -NoProfile -ExecutionPolicy Bypass -File scripts\verify-full-stack.ps1
powershell -NoProfile -ExecutionPolicy Bypass -File scripts\start-async-lab.ps1 -Mode local
powershell -NoProfile -ExecutionPolicy Bypass -File scripts\start-async-lab.ps1 -Mode mq
docker compose -f docker-compose.prod.yml --env-file .env.example config --quiet
```

只改文档不需要重复跑 Maven；至少执行 `git diff --check` 和链接/陈旧表述扫描。
