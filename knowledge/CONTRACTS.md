# 契约知识

机器可验证契约位于 `contracts/`。本文解释兼容策略与责任，不复制完整 schema。

## 共同信封

跨服务调用和事件至少携带：

- `tenant_id`：数据隔离主边界。
- `owner_id`：资源所有者；团队共享必须通过显式授权关系表达。
- `trace_id`：贯穿上传、转写、摄取、问答和审批。
- `event_id`：消息投递幂等键。
- `occurred_at`：带时区的业务发生时间。
- 资源 ID 与资源版本：防止旧事件覆盖新事实。

## 首个领域事件

`transcript.ready.v1` 表示某个媒体资产的一版转写已经成为可消费事实。它包含媒体元数据和有序片段，每个片段具有稳定 ID、`start_ms`、`end_ms`、可选说话人和文本。

机器契约为 `contracts/events/transcript-ready-v1.schema.json`，Agent 接收端点为 `POST /internal/v1/media/transcripts`，使用独立 Bearer 服务凭证，不接受用户 JWT 代替服务身份。

消费者按 `event_id` 去重，并按 `asset_id + transcript_version` 保证语义幂等。重复投递应返回成功；同一版本内容冲突应拒绝并告警。

生产者在媒体任务完成的同一数据库事务写 outbox，成功收到 Agent 的 2xx 后标记 SENT；409 视为不可自动覆盖的契约冲突，其余网络/服务错误按上限退避重试。事件不直接携带媒体存储路径。

## 证据引用

Agent 对外返回的通用证据结构区分 `document` 与 `video`。视频引用至少包含：

- `source_type=video`
- `asset_id`
- `segment_id`
- `start_ms`、`end_ms`
- 可选 `speaker`
- 引用文本与检索分数

引用中不包含永久公开 URL。前端使用资产身份向 Media Service 申请短期播放授权。

批准知识为了兼容既有客户端，对外仍使用 `source_type=document`，同时增加 `origin_type=approved_knowledge`，并可返回 `knowledge_candidate_id`、`prd_version_id`、`content_sha256`、知识版本和当前生命周期状态。历史回放还可返回 `superseded_by_document_id`。这些可选 provenance 字段由 `contracts/http/evidence-source-v1.schema.json` 约束；普通上传文档使用 `origin_type=uploaded_document`，视频使用 `origin_type=media_transcript`。

统一访问令牌 V1 声明由 `contracts/identity/jwt-claims-v1.schema.json` 定义；V2 契约 `contracts/identity/jwt-claims-v2.schema.json` 新增必填 `workspace_type` 与 `identity_version=2`。Agent 校验配置选定的算法（轻量 HS256 或生产试点 RS256/JWKS）、签名、issuer、audience、时间窗口、`token_use=access`、tenant、subject、role 与 jti；开发兼容身份头不会在 production 模式启动。兼容 V1 令牌读取时缺失 `workspace_type` 按 team 处理，使自批权限失败关闭。

统一前端只保存注册/登录返回的 access token；调用两个后端都使用 Bearer JWT。前端的视频筛选通过 `/chat` 的 `asset_ids` 收窄范围，不能扩大 JWT 已限定的 tenant/owner 范围。

生产试点的身份交换分两层：浏览器使用 OIDC Authorization Code + PKCE 获取 Keycloak access token，再通过 `POST /api/auth/oidc/exchange` 交给 Media；Media 校验外部 issuer/audience/signature 后返回内部 active-Workspace token。`GET /api/auth/jwks` 遵循 `contracts/identity/jwks-v1.schema.json`，只发布 RS256 公钥材料。Agent 不接受 Keycloak 令牌直接访问业务资源。

身份交换接受可选 `X-Workspace-Id` 请求头，用于续期时请求保持当前 Workspace；该值仅是选择参数，Media 必须重新读取已验证用户的成员关系及当前角色。省略时返回个人 Workspace；不存在或无成员关系时返回 404，外部令牌无效时返回 401。浏览器仅在 Workspace 404 后重新交换个人令牌，不能把网络故障、401/403 或 5xx 当作切换授权。返回值沿用 `AuthResponse`，平台 JWT 仍遵循身份契约 V2。

团队 Workspace HTTP 契约由 `contracts/http/workspace-collaboration-v1.schema.json` 定义：

- `GET /api/workspaces`：列出当前用户的全部个人/团队成员关系。
- `POST /api/workspaces`：创建 team Workspace，当前用户成为 OWNER。
- `GET /api/workspaces/{tenantId}/members`：列出同 Workspace 成员。
- `POST /api/workspaces/{tenantId}/invitations`：OWNER/ADMIN 创建一次性短期邀请码。
- `POST /api/workspaces/invitations/accept`：已登录用户消费邀请码并以 MEMBER 加入。
- `PATCH /api/workspaces/{tenantId}/members/{userId}`：OWNER 调整非 OWNER 成员为 VIEWER/MEMBER/ADMIN。
- `POST /api/workspaces/{tenantId}/switch`：服务端重新查询成员关系并签发该 active Workspace 的 V2 JWT。
- `GET /api/workflow/runtime`：除处理/存储模式外，返回 JWT 算法、OIDC、当前 Workspace 模型出境许可及 30/180/365 天保留配置；机器契约为 `contracts/http/media-runtime-v1.schema.json`。

六阶段分析使用 `POST /analysis/sessions` 创建会话，`POST /analysis/sessions/{id}/confirm` 携带当前 `resume_token` 和结构化答案恢复。读取与恢复都按服务端 JWT 的 tenant/owner 定位；错误租户返回不存在，避免泄漏资源是否存在。响应由 `contracts/http/analysis-session-v1.schema.json` 约束，并返回 `checkpoint_version`、`evidence_revision`、`evidence_snapshot_sha256` 与固定的 `retrieval_mode=hybrid`。快照正文不通过该契约公开；同一 token 的竞争确认只有一次 CAS 能成功，其余返回 409。

PRD 发布契约：

- `POST /analysis/sessions/{id}/publication/request`：`DRAFT_READY → PUBLISH_PENDING`，返回一次性审批 token 与策略。
- `POST /analysis/sessions/{id}/publication/approve`：校验 request ID、token、明确 `confirmation=PUBLISH`、Workspace 类型和职责分离后进入 `PUBLISHED`。
- `GET /analysis/publication-queue`：只向 team Workspace 的写角色返回其他提交者的待审批 PRD。
- `GET /analysis/sessions/{id}/audit`：返回发布申请与批准的 actor、role、策略和时间，不返回审批 token。
- `GET /analysis/sessions/{id}/deliverables`：读取已发布 PRD 的不可变版本、知识候选、知识版本链、生命周期申请和行动项草稿，响应契约为 `contracts/http/publication-deliverables-v1.schema.json`。
- `POST /analysis/sessions/{id}/knowledge-candidates/{candidateId}/lifecycle-requests`：申请 `SUPERSEDE` 或 `REVOKE`；替代必须携带新陈述和证据。
- `POST /analysis/sessions/{id}/knowledge-candidates/{candidateId}/lifecycle-requests/{requestId}/decision`：决定生命周期申请；team 请求者不得自批。请求与版本响应由 `contracts/http/knowledge-lifecycle-v1.schema.json` 约束。
- `POST /analysis/sessions/{id}/knowledge-candidates/{candidate_id}/decision`：对仍为 `PENDING` 的候选做一次性批准/拒绝；个人 owner 明确决定，team 由不同写角色成员决定。批准响应以 `contracts/http/approved-knowledge-v1.schema.json` 为契约，必须返回非空 `knowledge_document_id`、`knowledge_content_sha256` 和 `knowledge_published_at`；拒绝响应保持这些字段为空。
- `POST /analysis/sessions/{id}/action-items/{action_item_id}/ticket-draft`：只生成受控工具的 pending action，不直接创建工单；重复请求返回同一关联。审批结果会把行动项投影为 `TICKET_CREATED/REJECTED/FAILED`，成功时保存 `ticket_id`。

个人策略允许原 OWNER 完成第二次确认；团队策略拒绝 `requested_by == approved_by`。审批 token 在成功后清空，状态转换、审计、不可变 PRD 版本和初始派生交付物写入同一事务。

知识批准采用另一条原子边界：候选 CAS、托管知识 document/chunk、图索引和 provenance 在同一数据库事务提交。通用文档删除接口拒绝删除 `source_type=knowledge` 的托管记录，避免绕过治理接口破坏已批准事实。

## 会话问答与 SSE V1

`contracts/http/chat-conversation-v1.schema.json` 定义 `/chat` 与 `/chat/stream` 的兼容新增字段和事件信封：

- `conversation_id` 可空；`memory_mode=none|window|summary` 默认 `none`，不传会话字段的旧客户端仍为无状态问答。携带会话 ID 即使选择 `none` 仍会记录该会话，但不用历史补全。
- `ChatResponse` 新增可空 `conversation_id`、`exchange_id` 与 `follow_up`，原 answer/sources/trace 等字段保留。
- `POST /chat` 返回 JSON；`POST /chat/stream` 接受同样请求，以 Bearer JWT 鉴权，发送 `text/event-stream`。`GET /conversations/{conversation_id}` 返回授权会话的 revision 与最近最多 50 个已完成轮次。
- SSE 事件为 `plan`、`stage`、`delta`、`sources`、`follow_up`、`done`、`error`，共同包含 type/content/timestamp/conversation_id/exchange_id。15 秒空闲心跳是注释帧。`delta.content.text` 是待核验文本，`done.content` 才是最终审核后的 `ChatResponse`；客户端不得把断流前的片段当作完整回答。
- 个人会话绑定 tenant + owner，团队会话绑定 tenant；ID 本身不授予权限。未知或越权会话返回 404，领取冲突在响应头之前返回 409；SSE 已开始后的失败发送脱敏 `error`。停止通过取消 fetch 完成，没有独立停止或自动重放端点。
- 文档来源可新增 `parent_key` 与 `chunk_indices`，锚点 `chunk_index` 保留；只扩展同文档同章节的授权相邻块，并遵循问题主题和字符预算。视频片段不合并，原时间戳身份不变。机器约束见 `evidence-source-v1.schema.json`。

## 缓存可观测性

已鉴权的 `GET /embeddings/status` 以 `contracts/http/cache-observability-v1.schema.json` 为响应契约，在原 Embedding 覆盖率字段之外返回 `cache`：

- `embedding_vectors`：BGE 进程内向量 LRU 的条目数、容量、命中、未命中、请求数和命中率。
- `chunk_snapshots`：按 content revision 与 tenant/owner/asset 授权范围分键的 Chunk 快照 LRU 指标。
- `scope=process`：全部计数只代表当前 Agent 进程，进程重启后归零；多实例部署不能直接把任一实例视作全局值。

公开的 `GET /system/status` 仍只返回 Embedding 覆盖情况，不返回缓存请求量和命中计数。缓存契约只包含聚合数字，不包含原文、文本摘要、tenant、owner、asset 或缓存 key；这是有意的最小暴露边界。新增 `cache` 是已鉴权 Embedding 状态响应的扩展，消费者仍应按兼容策略忽略未知字段。

## 媒体运行能力可见性

已鉴权的 `GET /api/workflow/runtime` 由 `contracts/http/media-runtime-v1.schema.json` 约束。除调度、并发配额和存储类型外，响应必须明确给出 `transcriptMode=mock|whisper-api` 与 `summaryMode=mock|llm-api`。Web 必须据此标记“验证模式”或“真实处理模式”，不得仅凭任务成功就把 mock 转写包装成真实 AI 能力。

## 媒体阶段记录

`GET /api/workflow/tasks/{taskId}/stages?after=0&limit=50` 沿用任务 JWT/tenant/owner 范围，team 成员含 viewer 可读，跨 scope 返回不存在。数据部分由 `contracts/http/media-task-stages-v1.schema.json` 约束：`items`、`nextCursor`、`hasMore`，limit 为 1–100，after 是排他 ID 游标。

阶段只包含实际执行的 STORAGE_RESOLVE、AUDIO_EXTRACTION、TRANSCRIPTION、SUMMARY、RESULT_REUSE、RESULT_COMMIT、DELIVERY；记录独立 runId、时间和耗时，状态为 RUNNING/SUCCEEDED/FAILED/ABANDONED。失败仅返回枚举错误码，不包含正文、存储路径、凭证或 lease token。旧任务不补造历史，mock 不虚构抽音频。处理任务 lease 恢复会将旧处理阶段标为 ABANDONED，独立 DELIVERY 的硬崩溃残留 RUNNING 暂不自动关联关闭。

## 版本策略

- 事件名称带版本后缀。
- 新增可选字段可留在当前版本；删除、改义、改变必填性需发布新版本。
- 生产者、消费者和 schema 都必须有契约测试。
- 未知可选字段应被消费者忽略；未知事件版本不得静默降级处理。
