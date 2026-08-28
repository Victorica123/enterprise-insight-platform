# 架构知识

## 逻辑边界

```text
React Web
  ├─ /api/media/*  -> Media Service (Spring Boot)
  └─ /api/agent/*  -> Agent Service (FastAPI)

Media Service
  ├─ media metadata / processing tasks
  ├─ object storage / ffmpeg / transcription
  └─ transcript.ready.v1 -> Agent Service ingestion

Agent Service
  ├─ evidence segments / indexes / retrieval
  ├─ analysis sessions / confirmation checkpoints
  ├─ PRD drafts / approvals / action items
  └─ evidence-backed answers and evaluations
```

两个服务共享身份语义和跨服务契约，不共享数据库表。前端可以聚合展示媒体状态与分析状态，但后端不把两套状态压成一个易失真的枚举。

## 服务职责

### Media Service

- 拥有媒体资产、上传会话、对象存储位置和处理任务。
- 负责转码、抽音频、语音识别、重试、失败原因和媒体可用性。
- 产出带稳定片段 ID、时间段、说话人和文本的转写版本。
- 只向 Agent 发送必要业务字段，不泄露对象存储密钥或临时播放凭证。

### Agent Service

- 幂等接收媒体证据，进行切分、索引和检索。
- 拥有对话、分析会话、知识、PRD、审批和行动项。
- 对模型输出执行结构验证、证据校验、权限检查和审批门禁。
- 视频引用只持有媒体逻辑身份和时间范围，播放授权仍由 Media Service 颁发。
- 摄取同时按 `event_id` 和 `tenant_id + asset_id + transcript_version` 两级去重；相同键内容冲突返回 409 并保留旧事实。

### React Web

- 一个登录态、一个导航体系和一个任务工作台。
- 不承担权限判定；只呈现服务端能力和可解释的失败状态。
- 通过证据引用请求 Media Service 的授权播放地址并定位时间段。

## 可靠性边界

- 媒体任务状态：排队、处理中、完成、失败，可重试。
- Agent 分析状态：草稿、运行、等待确认、完成、失败、取消，可恢复。
- 跨服务投递采用版本化事件、`event_id` 幂等和可重放设计。
- 外部基础设施的 light/mock 模式仅用于开发；生产声明必须由真实集成 smoke 支撑。

## 迁移原则

原始 Video Platform 与 Agent Platform 仓库历史已导入本仓库；原仓库保持不动。整合通过纵向链路逐步替换旧入口，未迁移能力不会被无验证删除。
