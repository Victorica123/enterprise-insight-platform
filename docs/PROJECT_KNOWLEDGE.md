# Project Knowledge Base

本文件是项目当前方向、能力边界和文档导航的唯一总入口。模型启动时先读 `AI_STARTUP_HARNESS.md`；需要理解产品方向或选择下一项工作时再读本文件。

## 当前定位

> 一个可在本地完整复现的视频内容平台和后端工程实验室。

用户可完成注册登录、视频上传、异步处理、转写与摘要查看、播放、重试、删除和历史管理。项目通过真实本地 Redis、RocketMQ、MySQL、MinIO 与页面实验，解释大文件上传、慢任务、高并发削峰、幂等和故障恢复。

公网部署是已保留的可选能力，不是完成项目、学习或面试演示的前置条件。

## 价值排序

1. 用户能看见并验证完整业务流程。
2. 工程能力有测试、脚本、指标或页面证据。
3. 新手能复现、理解并在面试中准确表达。
4. 架构保持可切换、可调试，不为堆技术而扩张。

## 当前业务链路

```text
JWT 登录
  -> 普通上传 / Redis 分片续传 / MinIO 预签名直传
  -> 创建 VideoTask(QUEUED)
  -> 本地 @Async / RocketMQ
  -> FFmpeg -> Whisper 兼容转写 -> LLM 兼容摘要
  -> COMPLETED / FAILED
  -> 查询、播放、导出、重试、删除
```

## 已实现能力

| 领域 | 当前能力 | 主要证据 |
| --- | --- | --- |
| 身份与隔离 | JWT；上传、任务、播放、重试、删除按 owner 隔离 | 自动化测试、`VERIFICATION_MATRIX.md` |
| 大文件上传 | Redis 分片、状态查询、断点续传、合并锁、MD5 校验、秒传 | 页面、测试、完整栈脚本 |
| 对象存储 | MinIO/S3 预签名 PUT 直传、完成回调幂等、预签名播放 | `P4_OBJECT_STORAGE.md` |
| 异步处理 | 本地 `@Async` 与 RocketMQ 两种分发模式 | `ASYNC_LAB.md`、`LOADTEST.md` |
| 可靠性 | 幂等 claim、短事务状态机、失败重试、卡住任务 reaper | `P3_RELIABILITY_VERIFICATION.md` |
| 生命周期 | 终态删除、共享路径保护、持久化媒体清理重试、过期分片回收 | 页面、生命周期测试、清理指标 |
| 过载保护 | 每用户活动任务配额、429；本地线程池饱和、503 | 页面实验、并发测试 |
| 结果交付 | 转写、摘要、复制、Markdown 下载、Range/预签名播放 | 前端与 API 测试 |
| 可观测性 | Actuator、Prometheus/Grafana 配置、任务指标、验证输出 | `VERIFICATION_MATRIX.md` |
| 可选部署 | Docker Compose、Caddy HTTPS、体检与部署验证脚本 | P5 两份文档 |

当前自动化测试基线为 85 个。完整栈和 A/B 的真实数据见 `AI_HANDOFF.md`，不要把实验结果外推为生产容量。

## 模式选择

- **轻量业务演示**：H2、本地文件、本地异步、Mock AI；不依赖 Docker。
- **完整本地工程验证**：MySQL、Redis、RocketMQ、MinIO；验证中间件链路和可观察状态。
- **异步 A/B 实验**：保持请求量、文件、Mock 延时和 worker 数一致，只切换本地异步/MQ。
- **真实 AI smoke**：可选，只用于验证 API 接入，不进入默认测试。
- **公网部署**：可选架构扩展，不是当前必做路线。

## 当前完成度与可选增强

### 已完成：媒体生命周期

处理中任务不能被删除；终态任务删除与媒体清理任务在同一短事务登记。最后一份本地/MinIO 媒体会删除，共享路径会保留，存储删除失败由持久化任务自动重试，结果在页面可见。

用户可验证情景：完成上传后删除任务，页面提示原视频已清理；处理中的任务没有删除按钮；共享路径和失败重试由自动化测试覆盖。

### 已完成：本地会话过期治理

活动分片上传会刷新 Redis 元数据、分片集合和进行中映射的 TTL；过期 Redis 会话留下的磁盘目录会按保留期安全扫描、删除并记录指标；秒传缓存命中前会验证媒体仍存在。

独立 upload-session 数据库表只在未来需要长期运营审计时增加，不属于本地平台完整性的必要条件。

### 下一项：统一验证入口

把轻量启动、完整栈 smoke、MinIO 直传和异步 A/B 收敛为少量脚本及清晰结果，降低新机器和新模型接手成本。

### 可选：真实 AI

在用户有受控 API 配额时，用短视频验证一次真实转写与摘要，记录耗时、费用边界和错误诊断；默认继续使用 Mock 保证测试稳定。

## 当前非目标

- 购买云服务器、域名或维持公网实例。
- 声称已有生产用户、SLA、营收或真实线上峰值。
- 为面试堆叠 Kubernetes、微服务、服务网格等无验证价值的技术。
- 在没有业务问题时继续拆服务或增加中间件。
- 用 Mock 压测结果声称真实 AI 吞吐。

## 文档状态

| 文档 | 状态 | 用途 |
| --- | --- | --- |
| `../README.md` | 当前 | 项目总览、运行方式、事实边界 |
| `AI_STARTUP_HARNESS.md` | 当前 | 模型每次启动必读的紧凑缓存 |
| `AI_HANDOFF.md` | 当前 | 最新代码状态、证据、风险和下一步 |
| `CAREER_ROADMAP.md` | 当前 | 求职表达、演示顺序、学习路线 |
| `VERIFICATION_MATRIX.md` | 当前 | 功能到证据的映射 |
| `ASYNC_LAB.md` | 当前 | 页面驱动的本地异步/MQ 实验 |
| `LOADTEST.md` | 当前 | MQ A/B 方法与数据边界 |
| `P3_RELIABILITY_VERIFICATION.md` | 当前 | 可靠性验证与面试解释 |
| `P4_OBJECT_STORAGE.md` | 当前 | MinIO/S3 直传和播放 |
| `P5_SMALL_SCALE_DEPLOYMENT.md` | 可选 | 单机公网部署能力，不属当前主路线 |
| `P5_BEGINNER_LAUNCH_GUIDE.md` | 可选 | 新手公网部署步骤 |
| `TROUBLESHOOTING.md` | 历史证据 | 已遇到问题及修复记录 |
| `AGENT.md` | 历史模块说明 | 旧爬虫模块交接，不是全项目入口 |

## 按问题读取

- 最新跨模型进度：`AI_HANDOFF.md`
- 页面演示：`DEMO_SCRIPT.md`
- 求职与面试：`CAREER_ROADMAP.md`、`../INTERVIEW_GUIDE.md`
- MQ 是否“加速”：`ASYNC_LAB.md`、`LOADTEST.md`
- 失败恢复：`P3_RELIABILITY_VERIFICATION.md`
- MinIO/直传：`P4_OBJECT_STORAGE.md`
- 可选上线：`P5_SMALL_SCALE_DEPLOYMENT.md`、`P5_BEGINNER_LAUNCH_GUIDE.md`
- 故障排查：`TROUBLESHOOTING.md`
