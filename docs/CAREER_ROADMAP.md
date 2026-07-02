# 视频内容理解平台路线图

这份文档用于把本项目从“能跑的练习项目”推进成“能解决真实问题、能上线给用户使用、能支撑求职表达和学习复盘”的后端业务项目。

## 项目定位

本项目后续定位为：

> 一个面向真实用户的视频内容理解平台，重点解决大文件视频上传、高并发处理、异步 AI 工作流和线上可用性问题。

业务主线表达：

> 用户上传大视频时，系统通过分片上传、并发传输、秒传/断点续传、异步任务队列和资源隔离压缩等待时间；后台再完成 FFmpeg 音频提取、Whisper 转写和 LLM 总结，最终让多个用户可以稳定获得视频理解结果。

面试时主线表达：

> 这个项目不是简单 CRUD，而是围绕“大文件传输慢、高并发上传容易拖垮服务、AI 处理耗时长”这些真实业务瓶颈做架构设计。上传链路用 Redis 分片会话、TTL、锁和幂等保证可靠性；处理链路用本地异步或 RocketMQ 解耦；线上目标是支持真实用户使用、可观测、可扩容、可恢复。

## 核心业务目标

最高原则：

> 先完成用户真实需求，再用工程优化解决需求落地过程中的瓶颈。

大文件传输、高并发、服务器上线、测试和可观测性都不是独立目标，它们只在能帮助真实用户更顺畅地完成“上传视频 -> 获得可用理解结果 -> 管理历史任务”时才优先推进。

后续最高优先级目标：

1. **完成用户核心链路**：注册/登录、上传视频、稳定处理、返回转写和总结、查看历史任务。
2. **改善用户等待体验**：上传进度、任务状态、失败原因、重试提示、历史结果管理。
3. **压缩大文件上传耗时**：并发分片上传、断点续传、秒传、合理 chunk size、上传进度和失败重试。
4. **支撑真实用户访问**：生产数据库、服务器部署、HTTPS、域名、日志、监控、备份和文件清理。
5. **支撑高并发上传和处理**：限流、队列削峰、线程池隔离、任务状态机、幂等和重复请求保护。
6. **形成可验证的工程指标**：上传耗时、任务排队时间、处理耗时、失败率、并发数、资源占用。

这些目标优先级高于单纯“页面好看”“测试数量增加”或“为了技术而技术”。页面、测试和架构优化继续做，但必须服务于真实需求验证。

## 简历表达

可放入简历的项目描述：

- 基于 Spring Boot 3 + Java 17 实现多用户视频内容理解平台，支持 JWT 登录、用户隔离、视频任务状态查询。
- 设计 Redis 分片上传流程，使用 upload session、chunk set、TTL 和分布式锁保证合并安全性与用户权限隔离。
- 实现异步视频处理工作流：FFmpeg 音频提取、Whisper 转写、LLM 摘要生成，支持本地 `@Async` 与 RocketMQ 两种调度模式。
- 通过条件装配支持本地开发、Redis 模式、MQ 分布式模式，降低开发和部署环境成本。
- 补充单元测试覆盖文件校验、任务失败状态、错误信息截断、空转写摘要等关键边界。

不要虚构指标。可以使用真实指标，例如：

- 支持 3 种部署模式。
- 当前覆盖 12+ 个自动化测试。
- 工作流错误信息限制为 2000 字符，避免日志无限写入数据库。
- 支持 256MB 上传限制。

## 面试讲解结构

### 1. 业务链路

按这个顺序讲：

1. 注册/登录，后端签发 JWT。
2. 用户上传视频，单文件或分片上传。
3. Redis 保存上传会话和分片状态。
4. 合并完成后创建 `VideoTask`。
5. `WorkflowPublisher` 发布任务。
6. 本地异步或 RocketMQ 消费任务。
7. FFmpeg 提取音频。
8. Whisper 转写。
9. LLM 生成总结。
10. 用户查询自己的任务结果。

### 2. 技术亮点

优先讲这些：

- 条件装配：同一套代码支持本地、Redis、Redis + MQ。
- 用户隔离：上传 session 和任务查询都绑定 owner。
- 事务边界：工作流状态更新在 `@Transactional` 方法内完成。
- 资源清理：FFmpeg 临时文件在异常/超时路径清理。
- 失败可观测：任务失败落库，错误信息截断。
- 测试隔离：测试不依赖 Redis、RocketMQ、Docker、外部 AI API。

### 3. 架构取舍

可回答的问题：

- 为什么不是一开始就强依赖 MQ？
- 为什么开发模式可以关闭 Redis？
- 为什么外部 AI 客户端要有 mock fallback？
- 为什么状态更新不能每一步都 `save()`？
- 为什么上传合并需要锁？

## 后续迭代策略

从 2026-06-30 开始，后续迭代改成“可展示的产品效果优先”：

- 优先做打开页面就能看到、能演示、能截图、能写进简历的改动。
- 后端测试和代码质量继续做，但定位为验收手段，不再作为对你最主要的阶段反馈。
- 每次进展用更短格式记录：`Done`、`Interview point`、`Verified`。
- 面试讲解以“这个项目如何满足一个真实需求”为主线：上传视频 -> 自动处理 -> 返回转写和总结 -> 用户隔离查询历史任务。

从用户最新规划开始，后续主线进一步升级为“真实业务性能和上线优先”：

- 优先完成用户真实需求；大文件上传耗时、高并发稳定性、后台处理削峰、服务器上线是需求落地时要解决的工程问题。
- 每个性能优化都要设计可验证指标，例如同一文件上传耗时、并发上传成功率、任务平均排队时间。
- 每个上线改动都要考虑真实用户影响，例如数据持久化、文件清理、失败重试、日志定位、容量限制。
- 面试表达从“我做了某个组件”升级为“我围绕具体瓶颈做了架构取舍，并用实验验证效果”。

从后续迭代开始，遇到真实工程问题时按这个格式沉淀：

- `Symptom`: 你能看到的现象，例如启动失败、Health 返回 DOWN、上传 503、任务卡住。
- `Cause`: 工程原因，例如可选依赖和健康检查不一致、旧 token、事务回滚、端口占用。
- `Fix`: 代码、配置或流程上的解决方案。
- `Verify yourself`: 给你一个可以亲自操作的验证场景，而不是只看我说“已修复”。
- `Interview point`: 这个问题在后端面试里对应的知识点。

当前主线：

1. 明确并完成核心用户需求：用户能上传视频、等待处理、拿到可用结果、回看历史任务。
2. 建立体验和性能基线：记录当前上传、处理、等待、失败的真实表现。
3. 按需求瓶颈优化大文件传输：并发分片、断点续传、秒传、重试、chunk size 调优。
4. 为真实用户上线做准备：MySQL migration、Docker 部署、Nginx/HTTPS、日志和监控。
5. 当出现真实并发压力时优化高并发处理：限流、线程池隔离、队列削峰、幂等、状态机保护。
6. 保持可展示产品面：页面用于展示业务闭环和用户价值，不只是装饰。
7. 用真实工程问题做学习场景：启动、健康检查、鉴权失效、上传失败、任务卡住、依赖降级。

## 后续迭代阶段

### Phase 1: 可展示性

目标：让面试官 3 分钟内看懂项目。

任务：

- 整理 README 的运行说明，修复乱码。
- 新增 API 文档入口，优先选择 Springdoc OpenAPI。
- 写一个 `DEMO_SCRIPT.md`，记录演示步骤。
- 确保 `start-video-service.ps1` 一键启动路径清晰。

验收：

- 新人按 README 可以在本地启动。
- 打开浏览器可以完成注册、登录、上传、查询任务。
- 面试时可以展示 API 页面或接口清单。

### Phase 2: 产品演示面增强

目标：让你和面试官不用读代码，也能看懂项目如何解决需求。

任务：

- 首页增加“面试演示/架构说明”区域，展示业务链路、运行模式和 API/健康检查入口。
- 处理结果区增加状态流水线：上传、排队、转写、总结、完成/失败。
- 我的任务列表强化“历史结果可追踪”的产品表达。
- README 和 `DEMO_SCRIPT.md` 保持与页面演示步骤一致。

验收：

- 打开首页 30 秒内能看懂系统链路。
- 演示时可以从页面跳转 Swagger 和 Health。
- 上传一个视频后，任务状态变化能在页面上直观看到。

### Phase 3: 大文件上传性能基线

目标：先量化“现在慢在哪里”，再优化。

任务：

- 增加上传耗时统计：init、chunk upload、merge、task created。
- 前端展示上传总耗时、平均分片耗时、失败重试次数。
- 准备 50MB / 200MB / 500MB 测试文件的验证方案。
- 记录当前单文件上传和 Redis 分片上传的基线数据。

验收：

- 能回答“当前上传一个 200MB 文件大概耗时多少，慢在上传还是 merge”。
- `TROUBLESHOOTING.md` 或新文档中有可复现实验步骤。
- 面试能讲“先测量，再优化”，而不是凭感觉调代码。

### Phase 4: 大文件传输提速

目标：压缩大文件上传等待时间。

任务：

- 前端实现并发分片上传，控制并发度，例如 3-5 个 chunk 同时上传。
- 后端保证 chunk 写入线程安全和边界校验。
- 支持失败 chunk 重试和已上传 chunk 跳过。
- 评估 chunk size 对耗时、内存、失败重传成本的影响。
- 完善秒传/断点续传体验，让重复上传更快返回。

验收：

- 同一测试文件上传耗时相比基线下降。
- 单个 chunk 失败后只重试失败 chunk，不重传整个文件。
- 重复上传同一文件能走秒传或快速恢复。

### Phase 5: 高并发与削峰

目标：多用户同时上传和处理时，系统不被拖垮。

任务：

- 增加上传接口限流或并发保护，避免单用户占满资源。
- 拆分上传线程池、工作流处理线程池、外部 API 调用并发。
- RocketMQ 模式下完善重复消息幂等：已完成任务不重复执行。
- 增加任务队列状态和排队时间记录。
- 为任务状态机增加非法状态推进保护。

验收：

- 多个用户并发上传时，失败率和响应时间可观察。
- 重复提交 merge 不产生重复任务或脏文件。
- 重复消费同一 taskId 不重复处理已完成任务。
- 面试能讲“限流、队列、幂等、锁、状态机”的区别。

### Phase 6: 测试与质量证据

目标：证明项目不是“只在我电脑上能跑”。

任务：

- 补充 Controller 层测试：鉴权、401、403、用户隔离。
- 补充上传服务测试：文件校验、越权 uploadId、缺失 chunk。
- 补充工作流测试：成功、转写失败、总结失败、错误截断。
- 将测试配置集中到 `src/test/resources/application-test.yml`。

验收：

- `mvn test` 稳定通过。
- 测试不需要 Redis、RocketMQ、Docker、外部 API key。
- 简历上可以写“覆盖核心业务边界测试”。

### Phase 7: 数据库生产化

目标：从 demo 数据库思维升级到生产后端思维。

任务：

- 引入 Flyway 或 Liquibase。
- 为 `user_account`、`video_task`、`crawled_video` 写初始化 migration。
- 明确 H2 本地模式和 MySQL 生产模式差异。
- 避免长期依赖 `ddl-auto=create-drop`。

验收：

- 本地 H2 能通过 migration 初始化。
- MySQL profile 能通过 migration 初始化。
- 面试能讲清楚“为什么生产不用 Hibernate 自动建表”。

### Phase 8: 服务器上线与真实用户使用

任务：

- 提供 Dockerfile。
- 提供 Docker Compose 一键启动 app + Redis + MySQL。
- 配置 Nginx 反向代理、HTTPS、上传大小限制和超时时间。
- 明确文件存储策略：本地磁盘、挂载盘或对象存储。
- 增加数据备份、日志保留、文件清理策略。
- 增加 GitHub Actions：编译、测试。

验收：

- 新服务器可以按文档部署完整链路。
- 外部用户可以注册、上传、查看任务。
- 上传大小、磁盘容量、日志路径、备份策略都有明确说明。
- 简历和 GitHub 首页都有清晰项目入口。

### Phase 9: 可观测性与排障

目标：能讲线上问题怎么发现、定位、修复。

任务：

- 增强 Actuator health/info。
- 增加结构化日志字段：taskId、uploadId、owner。
- 增加失败原因分类：上传失败、FFmpeg 失败、Whisper 失败、LLM 失败。
- 整理 `TROUBLESHOOTING.md`，保留真实问题记录。

验收：

- 一个失败任务可以通过日志和数据库定位原因。
- `GET /actuator/health` 能体现关键依赖状态。
- 面试能讲一次完整排障案例。

### Phase 10: 工程问题验证场景库

目标：把真实工程问题变成你能参与验证和复盘的训练材料。

任务：

- 为每个已遇到的问题补一张问题卡：现象、原因、修复、验证步骤、面试知识点。
- 优先整理这些高频场景：Docker 未启动导致启动失败、轻量模式 Health 503、旧 JWT 导致 403、Redis 关闭导致分片上传 503、非法视频导致任务失败。
- 在 `TROUBLESHOOTING.md` 中保留能复现的命令和预期结果。

验收：

- 你可以按文档独立复现至少 3 个问题。
- 每个问题都有“修复前会怎样、修复后应该怎样”的验证标准。
- 面试能讲清楚一次真实排障过程，而不是背概念。

## 每次迭代的固定流程

每次只做一个小阶段，按这个流程走：

1. 明确本次目标和验收标准。
2. 先跑当前测试，建立基线。
3. 做最小范围代码或文档修改。
4. 补对应测试。
5. 跑 `mvn test`。
6. 更新本文档的进度。
7. 总结这次迭代如何写进简历/如何面试讲。

## 当前建议的下一步

下一步先围绕用户核心需求确认当前链路，再推进 Phase 3：

1. 确认当前核心体验：注册/登录、上传、任务状态、转写总结、历史任务是否满足你想给用户的基本需求。
2. 对不满足需求的地方先补产品能力，例如失败提示、任务详情、重试入口、历史结果管理。
3. 再建立上传性能基线：记录当前上传耗时、分片耗时、merge 耗时。
4. 加一个你能看到的上传指标面板：总耗时、chunk 数、平均 chunk 耗时。

原则是：先让用户链路成立，再用性能基线证明哪里需要优化。

## 进度记录

- 2026-06-28: 完成 Phase 1：重写 README 快速启动和面试展示说明，接入 Springdoc OpenAPI，新增 `DEMO_SCRIPT.md`。
- 2026-06-30: Done: added security and owner-scope tests for Workflow, Crawl, and Media controllers, plus a real JWT bearer-token integration test. Interview point: backend APIs must prove authentication and user isolation, not only happy paths. Verified: 24 tests passing.
- 2026-06-30: Done: added ChunkUploadService owner, index, TTL, and file-write boundary tests. Interview point: upload security = auth owner check + idempotency/TTL + input bounds. Verified: 28 tests passing.
- 2026-06-30: Done: added mergeChunks tests for missing chunks, lock contention, cleanup, task creation, and publish. Interview point: merge is a side-effect workflow needing locks and cleanup. Verified: 31 tests passing.
- 2026-06-30: Done: shifted roadmap to visible product/demo outcomes first, added homepage interview demo panel, API/health links, task pipeline, and updated demo script. Interview point: a backend project should expose its business flow and architecture decisions clearly, not only hide value in code. Verified: `node --check src/main/resources/static/app.js` and `mvn test` passed with 31 tests.
- 2026-06-30: Done: added a new iteration rule for real engineering problems: summarize symptom/cause/fix and provide a user-verifiable scenario. Interview point: production engineering value comes from diagnosing observable failures and proving fixes, not just editing code. Verified: documentation-only update.
- 2026-06-30: Done: recorded the upgraded product direction: optimize large-file upload time, support high concurrency, and prepare server deployment for real users. Interview point: the project now has a real business bottleneck story: measure upload/processing latency, optimize transfer and queueing, then deploy with observability. Verified: documentation-only update.
- 2026-07-01: Done: corrected the roadmap priority to user needs first; large-file upload, concurrency, and deployment are implementation problems that serve the product goal, not standalone goals. Interview point: good backend engineering starts from user value, then solves the bottlenecks that block that value. Verified: documentation-only update.
- 2026-07-01: Done: started a maintainability pass: simplified workflow controller authentication handling, reshaped the frontend into a two-column operational workspace, added `PROJECT_KNOWLEDGE.md`, and updated the project Codex skill to use the knowledge entrypoint. Interview point: project quality includes code clarity, usable UI, and durable team knowledge, not only backend features. Verified: pending tests.
- 2026-07-01: Done: ran a focused engineering-optimization pass over the code added since 2026-06-13 (security, correctness, resource, cleanup) and recorded it in `TROUBLESHOOTING.md` → "代码优化与质量改进记录（2026-07-01）". Fixes: the HTTP 500 handler no longer returns raw internal exception messages to clients; `DistributedLockService.tryLock` now has identical fail-fast/lease semantics across the Redisson and Redis implementations, so a concurrent merge is rejected instead of silently duplicating the task; chunk-merge cleans up the half-written file on failure; removed an unused import; and corrected the now-stale `@Transactional` guidance in `CLAUDE.md` to match the per-stage short-transaction design. Interview point: an optimization only sticks if the code fix and the knowledge base move together — otherwise the next contributor "fixes" it back. Verified: `mvn -q clean test -Dapp.redis.enabled=false`, 33 tests green, no regression.

## 2026-07-01 收尾进展

- Done: added an upload experiment panel that switches between normal upload and Redis concurrent chunk upload. The metrics panel keeps the latest real upload result and separate recent results for both modes, so switching modes no longer rewrites previous records.
- Done: changed Redis chunk upload from serial chunks to browser-side concurrent chunks with concurrency `4`.
- Done: added owner-scoped task deletion from the history list through `DELETE /api/workflow/tasks/{taskId}`.
- Done: added Docker Compose MySQL profile and changed Redis host port to `7379` because Windows reserved `6379-6478` in this environment.
- Interview point: Redis chunk upload is a reliability/resume foundation first; speed comes from concurrent chunks, chunk-size tuning, retry, resume, and instant upload. RocketMQ is for post-upload task queueing and decoupling, not direct upload acceleration.
- Verified: `node --check src/main/resources/static/app.js`, `WorkflowControllerTests`, `mvn test` with 33 tests, service health `UP`, and `smoke-test.ps1`.
