# 架构知识

## 逻辑边界

```text
React Web
  ├─ /api/media/*  -> Media Service (Spring Boot)
  └─ /api/agent/*  -> Agent Service (FastAPI)

Media Service
  ├─ OIDC identity mapping / Workspace memberships / RS256 active-Workspace JWT issuance
  ├─ media metadata / processing tasks
  ├─ object storage / ffmpeg / transcription
  └─ transcript.ready.v1 -> Agent Service ingestion

Agent Service
  ├─ evidence segments / indexes / retrieval
  ├─ analysis sessions / confirmation checkpoints
  ├─ PRD drafts / publication approvals / immutable versions
  ├─ approved knowledge materialization / action-item drafts / tool approvals
  └─ evidence-backed answers and evaluations
```

两个服务共享身份语义和跨服务契约，不共享数据库表。生产试点可共用同一个 MySQL 实例，但 Media、Agent 与 Keycloak 使用独立 schema；前端可以聚合展示媒体状态与分析状态，但后端不把两套状态压成一个易失真的枚举。

## 工程知识维护平面

工程知识平面不参与客户请求：项目 Skill 调用 `scripts/knowledge_index.py`，从生成的维护语义索引取得 Top-K 文件、标题和行号，再回读人工知识原文。索引只覆盖仓库文档、ADR、契约与 Skill 参考，与 Agent Service 的 tenant 业务向量表完全隔离。chunk 内容指纹支持增量向量复用，corpus revision 同时驱动查询缓存失效；完整决策见 ADR-0007。

## 服务职责

### Media Service

- 拥有账号、个人/团队 Workspace、成员关系、一次性邀请与 active Workspace JWT 重签。
- 生产试点验证 Keycloak OIDC access token，将 `(issuer, subject)` 映射为内部用户，再以 RS256 签发短期 Workspace JWT；JWKS 只暴露公钥。
- 拥有媒体资产、上传会话、对象存储位置和处理任务。
- 负责转码、抽音频、语音识别、重试、失败原因和媒体可用性。
- 产出带稳定片段 ID、时间段、说话人和文本的转写版本。
- 媒体任务与内容去重资产都持久化结构化转写片段；内容命中复用时不会丢失时间戳证据。
- 内容去重资产按 `tenant_id + content_md5` 隔离，不能让一个租户复用或改变另一个租户的结果。
- 长时间处理任务使用可续租的数据库 fencing lease；阶段完成和失败写入带 lease 条件，过期任务由条件更新安全重入队，避免看门狗误判时覆盖活跃结果。
- 只向 Agent 发送必要业务字段，不泄露对象存储密钥或临时播放凭证。

### Agent Service

- 生产试点把全部业务存储切到独立 MySQL schema；SQLite 仅保留为开发和确定性验收基线。
- 幂等接收媒体证据，进行切分、索引和检索。
- 拥有对话、分析会话、知识、PRD、审批和行动项。
- 对模型输出执行结构验证、证据校验、权限检查和审批门禁。
- 在 PRD 发布 CAS 与审计的同一事务写入内容哈希版本、知识候选和行动项草稿。
- 在知识候选 CAS 的同一事务写入受治理知识文档、chunk、图索引和 provenance；任一写入失败时保持候选 `PENDING`。
- 在知识生命周期申请 CAS 的同一事务写入新版本或软撤回、候选当前指针、document 活跃状态、content revision 与 scope 图谱替换；历史 chunk 不删除。
- 视频引用只持有媒体逻辑身份和时间范围，播放授权仍由 Media Service 颁发。
- 摄取同时按 `event_id` 和 `tenant_id + asset_id + transcript_version` 两级去重；相同键内容冲突返回 409 并保留旧事实。

### React Web

- 一个登录态、一个导航体系和一个任务工作台；提供创建/加入团队、成员管理与显式 Workspace 切换。
- 不承担权限判定；只呈现服务端能力和可解释的失败状态。
- 通过证据引用请求 Media Service 的授权播放地址并定位时间段。

## 可靠性边界

- 媒体任务状态：排队、处理中、完成、失败，可重试；处理中的任务由 tenant-scoped 内容单飞、数据库 fencing lease 和过期条件重入队共同保护。
- Agent 分析状态：运行、等待确认、草稿就绪、待发布审批、已发布、失败，可恢复。
- 发布状态采用服务端 compare-and-set：`DRAFT_READY → PUBLISH_PENDING → PUBLISHED`，状态变更与审计事件在同一 SQLite 事务提交，避免并发重复批准。
- 分析创建先执行授权后 objective-aware hybrid 检索并固化证据 revision/hash；确认只使用冻结快照，保留阶段 1–4，并以 session/status/resume token 的数据库 compare-and-set 推进检查点。等待期间新增证据不会静默改写旧阶段结论。
- 发布版本按 canonical JSON 的 SHA-256 标识且不可覆盖；知识候选使用独立 CAS 决策。批准后生成内部 `source_type=knowledge` 的托管文档；替代生成新文档版本并把旧版软标记 `SUPERSEDED`，撤回把当前版本软标记 `REVOKED`。Retriever 与图谱只消费 `ACTIVE` 文档，历史聊天来源在回放时解析当前生命周期。公开证据保持兼容的 `source_type=document` 并用 `origin_type=approved_knowledge` 暴露治理来源。行动项通过幂等工具草稿进入审批，并把终态与真实 `ticket_id` 投影回交付物。
- 跨服务投递采用版本化事件、`event_id` 幂等和可重放设计。
- Media 的任务创建、人工重试和 stale requeue 会在同一数据库事务写入/重置 `workflow_dispatch_outbox`。独立 dispatcher 以 claim lease 把持久意图投递到本地 executor 或 RocketMQ；瞬时拒绝只退避重试，不再让上传接口在任务已经落库后返回失败。Worker 仍以任务状态 CAS、processing lease 和内容单飞抵御重复投递。
- Media 在任务完成事务内写入 `integration_event_outbox`；调度器先通过条件更新把可投递/过期记录领取为带 `claimId + claimExpiresAt` 的 `CLAIMED`，再通过 HTTP/1.1 投递。完成和失败写入继续校验 claim 持有者、lease 和 attempts；瞬时失败指数退避，契约冲突或重试耗尽进入 DEAD，Agent 端继续执行事件级与语义级双重幂等。该设计仍是 at-least-once，不声称 exactly-once。
- 外部基础设施的 light/mock 模式仅用于开发；生产声明必须由真实集成 smoke 支撑。
- 外部模型调用在生产中以签名 tenant 为白名单键，未批准 Workspace 即使配置了供应商 Key 也不能出境；Media/Agent 的保留期任务以有界批次清理媒体、视频转写和审计。

## 迁移原则

原始 Video Platform 与 Agent Platform 仓库历史已导入本仓库；原仓库保持不动。整合通过纵向链路逐步替换旧入口，未迁移能力不会被无验证删除。

## Agent Service 内部全景边界

架构图中的对话编排、检索与证据、三层执行器、知识底座、治理审批和工程护栏，分别由 `services/agent-service/app/architecture/` 下的六个 façade 暴露。façade 是应用入口和替换适配点，不拥有新的数据库表，也不改变 Media/Agent 两服务边界；旧实现模块继续保留以兼容既有测试和契约。详细映射、生产诚实边界与后续替换顺序见 [ARCHITECTURE_PANORAMA.md](../docs/ARCHITECTURE_PANORAMA.md)，决策见 [ADR-0015](decisions/0015-agent-service-bounded-context-facades.md)。
