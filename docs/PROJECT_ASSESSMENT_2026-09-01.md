# Enterprise Insight Platform 项目质量评估

> 评估日期：2026-09-01  
> 评估视角：资深全栈软件工程 / AI 工程  
> 评估范围：当前整合仓库、自动化测试、Agent 评测、知识契约与本地验收脚本  
> 结论性质：工程评估，不等同于生产发布批准

## 结论摘要

项目已经超过“两个 Demo 拼在一起”的阶段，形成了一个可演示、可回归、边界清晰的工程型试点基线。最有价值的部分不是页面数量，而是：Media Service 与 Agent Service 的职责边界、真实 JWT/tenant/owner 隔离、视频时间证据、分析冻结快照、PRD/知识/工具的人工审批，以及可重复的本地纵向验收。

但它目前仍不应被描述为生产就绪，也不应把确定性规则分析、闭集黄金集和本地 mock 链路包装为真实多 Agent 或开放域 LLM 能力。当前更准确的定位是：**工程型试点 / 面试交付基线，具备进入小规模真实集成试运行的条件，但尚未完成生产化门禁。**

### 综合判断

| 维度 | 判断 | 说明 |
| --- | --- | --- |
| 业务闭环 | 8/10 | 上传、转写、证据、问答、分析、PRD、知识和工单治理链路完整 |
| 架构边界 | 8/10 | 双后端职责清楚，跨服务事件和权限语义基本统一 |
| 工程正确性 | 7/10 | 幂等、CAS、证据校验和失败回滚较扎实；数据库/队列并发仍需真实环境验证 |
| AI 能力 | 5.5/10 | RAG 工程基线不错；六阶段当前是确定性 specialist，不是真正自主多 LLM Agent |
| 生产准备度 | 4.5/10 | 身份、迁移、容量、灾备、外部依赖和真实模型效果尚未完成证据闭环 |
| **总体定位** | **约 6.8/10** | 适合试点和展示，不适合直接承诺生产 SLA/ROI |

## 已验证的强项

1. **服务边界保持一致**：Media Service 管理上传、存储、转写和媒体任务；Agent Service 管理证据、检索、分析、PRD、知识和工单。没有把两套状态硬合成一个易失真的状态机。
2. **授权前置**：个人资源按 `tenant_id + owner_id`，团队资源按 tenant 共享读取并保留创建者归属；检索和图检索在查询阶段过滤，不依赖前端隐藏按钮或回答后删结果。
3. **证据可验证**：视频证据保存 asset、segment、`start_ms/end_ms` 和文本；治理写入会把请求/模型提供的证据重新解析到活动 chunk，并拒绝伪造的文件名、时间段或 excerpt。
4. **治理边界完整**：分析确认、PRD 发布、知识批准/替代/撤回、工具副作用均有独立状态门禁、审计、幂等或四眼约束；历史知识软失效而不是物理删除。
5. **恢复语义比普通 Demo 强**：分析会话冻结 evidence revision/hash，恢复使用 CAS；媒体任务当前增加了 tenant-scoped 去重、worker lease、心跳和过期条件重入队，避免简单的“进程内线程卡住即永久丢失”。
6. **降级和可测试性好**：无外部模型、MQ、Redis 或对象存储时仍可用本地 mock/light 路径验证主流程，且知识库、契约和质量证据可再生。

## 主要风险与问题

### P0：进入真实生产前必须解决

#### 1. 身份信任根仍不适合多服务生产

当前 Media 与 Agent 使用共享 HS256 secret 验证 JWT。这样任一服务发生密钥泄露，都可能伪造另一服务信任的用户令牌；Agent 也没有完整的即时撤权、密钥轮换和正式 IdP 证据。Media 默认 access token 有效期为 24 小时，角色变化只能等待令牌过期或黑名单路径生效。

建议：

- 采用 OIDC/OAuth2 IdP，服务只通过 JWKS 验证 RS256/ES256 公钥；签发私钥不进入业务服务。
- 严格校验 `iss/aud/sub/tenant_id/workspace_type/role/token_use/jti`，为服务身份使用独立 audience 和 mTLS 或短期 client credentials。
- 浏览器优先采用 HttpOnly/SameSite Cookie + BFF；若必须由 SPA 持有 bearer token，缩短 access token 生命周期并设计 refresh、撤权和 XSS 响应方案。
- 将 active Workspace、成员变更、令牌撤销写入正式 ADR 和真实 IdP smoke。

#### 2. 数据库 schema 仍是开发期策略

Media 的默认配置使用 `spring.jpa.hibernate.ddl-auto: update`，Agent 通过启动时 `CREATE TABLE/ensure_column` 自动修补 SQLite。多实例启动或大表变更时，自动 DDL、锁竞争和不可逆 schema 漂移都可能成为事故源。默认数据库账号/密码和部分存储凭据也属于明显的开发默认值。

建议：

- 正式选择 MySQL 或 PostgreSQL，并用 Flyway/Liquibase 版本化迁移；生产启动禁止隐式 schema update。
- 为 SQLite 保留本地验收 profile，但不把它作为 Agent 生产主库；引入迁移前后的备份、校验、回滚和演练。
- 禁止生产使用 root/123456、MinIO 默认 key 或 demo secret；启动时按环境 fail-closed。
- 对 `documents/chunks/graph/knowledge/audit/outbox` 建立约束、索引、保留和归档策略。

#### 3. 文件上传与媒体处理存在容量和安全边界

本轮已将 S3 fallback 改为流式 SHA-256 + `ofFile` 请求体，并在上传入口增加扩展名与容器 magic bytes 的一致性检查；仍未形成 ffprobe、时长/帧率/编解码限制、病毒扫描、multipart 大文件策略和 FFmpeg 资源隔离的完整防护。

建议：

- 浏览器优先走分片/直传；服务端 fallback 使用流式 multipart/chunk upload，禁止按文件大小线性占用堆内存。
- 以内容探测和 ffprobe 结果为准，限制时长、分辨率、帧率、码率、压缩炸弹和并发处理数。
- FFmpeg/解析器放到受限 worker 或沙箱，加入临时文件清理、病毒扫描、租户配额和审计。
- S3 配置必须去掉默认凭据，并验证 bucket、endpoint、TLS、最小权限和轮换。

#### 4. 生产级外部依赖和灾备尚未有证据

当前本地 acceptance 有价值，但明确使用临时 H2/SQLite、本地文件、mock/local AI 和随机 localhost 端口；Docker、真实 MySQL/Redis/RocketMQ/S3、外部模型、正式 IdP、故障注入、恢复点目标和告警联动还未形成可审计证据。因此不能从本地通过推导生产吞吐、可用性或 ROI。

### P1：试点扩大前完成

1. **持久化任务执行**：当前仍是本地线程池/同步 MQ consumer + 轮询 reaper。小规模可用，但不能提供执行栈级恢复。应先以真实负载确认需要，再选择 Temporal、现有 MQ 的 durable consumer，或数据库任务表 + lease worker；不要在没有容量数据前直接引入整套 Kubernetes。
2. **Outbox 多实例 claim（本轮已补基线，生产仍需真实验证）**：`IntegrationEventOutbox` 增加 `CLAIMED`、`claimId`、`claimExpiresAt`、`attempts`、`nextAttemptAt` 和 `lastError`；dispatcher 先以条件更新领取，再按持有者和 lease 有效期完成/失败，过期 claim 可接管，达到上限进入 `DEAD`。H2 集成测试覆盖单领取、过期接管、旧 worker 不能覆盖新 worker 和失败退避。仍需正式迁移、数据库方言/锁行为、告警和真实多实例故障注入证据。
3. **SQLite 到可扩展存储**：Agent 的进程内 chunk cache、哈希 embedding fallback 和 SQLite 全表/租户范围扫描适合试点。达到明确 chunk、QPS、并发和写入指标后，再迁移 PostgreSQL，并评估 Qdrant/pgvector 等支持 metadata pre-filter 的索引；不能只把向量库当成“更快的 SQLite”。
4. **真实 LLM 评测**：六阶段 `run_six_stage_analysis` 目前是固定模板/规则 specialist；V6、PRD、Knowledge Lifecycle 是闭集固定 fixture 的回归门禁，不等于开放域准确率。应固定 prompt/model/schema 版本，建立客户脱敏 holdout，评估引用支持率、拒答、冲突、成本、p95、重试和数据外泄。
5. **结构化模型输出（问答侧已补第一步）**：Router、Planner 和 Tool Agent 已通过统一 client 传递 provider-compatible `response_format`；OpenAI 使用 strict JSON Schema，DeepSeek 使用 JSON Object，随后仍执行类型、枚举、工具白名单和参数校验并保留规则降级。六阶段 specialist、答案引用的完整 Pydantic/schema 约束、evidence provenance 和 side-effect policy 仍需真实模型链路与 holdout 证据；模型输出永远是不可信输入。
6. **可观测性闭环**：采用统一 OpenTelemetry traces/metrics/logs resource 和语义命名；补齐队列积压、lease lost、outbox age/attempts、模型 token/cost、citation rejection、tenant deny、p95/p99 和告警到值班流程。

### P2：维护性和体验优化

1. 拆分 Web 的 `App`、`AnalysisWorkspace`、`QAView`：当前静态复杂度约为 48、87、62，fanout 约为 116、101 等；按领域组件、状态机、请求 hook 和错误边界拆分。
2. 统一请求取消、重试、轮询退避、过期 token、错误映射和加载状态；长分析和上传需要 AbortController、可恢复 UI 和明确的失败操作。
3. 对图谱大数据量做分页/虚拟化和服务端路径限制；补键盘导航、focus trap、屏幕阅读器标签、移动视口和错误边界。
4. 将上传、播放和证据时间定位做成单独的端到端浏览器 smoke；避免只验证 API 200 而没有验证用户真的能定位到媒体片段。

## 本轮继续任务的落地变更

- `services/media-service/.../VideoTaskRepository.java`：增加 lease 心跳、lease fencing 完成/失败写入、过期条件重入队查询和条件更新。
- `services/media-service/.../VideoTaskService.java`：媒体任务 claim 返回 lease；转写到摘要期间保持 lease；阶段写入、内容 fan-out 和失败 fan-out 以 lease 条件提交，避免 reaper 用旧实体快照覆盖活跃任务。
- `services/media-service/.../WorkflowProcessor.java`：长时间外部 I/O 期间心跳续租，lease 丢失时停止提交；内容去重 key 带 tenant。
- `services/agent-service/app/graph_rag.py`：修复 team scope 在图 Agent 中错误退回 `legacy` owner 的问题；团队图谱现在读取同 tenant 不同成员的实体，personal 仍保持 owner 隔离。
- `services/media-service/.../IntegrationEventOutboxRepository.java`、`TranscriptEventOutboxService.java` 和 `AgentOutboxDispatcher.java`：补充数据库条件 claim/lease、过期接管、持有者 fencing、退避与 DEAD 终态。
- `services/agent-service/app/llm_client.py`、`llm_router.py`：补充 OpenAI strict JSON Schema / DeepSeek JSON Object 兼容通道，以及结构化 envelope、工具参数解析和规则降级。
- 对应 Media/Agent 回归测试已更新，并新增 lease、outbox claim、结构化 LLM response format 和 team graph 负向/共享测试。
- `quality/agent-evals/evaluate_knowledge_lifecycle.py`、`evaluate_v5.py` 明确设置测试专用 development auth mode，避免生产默认 JWT 策略使闭集评测错误返回 401/422；生产服务仍保持 JWT-only。
- 已同步更新 `knowledge/ARCHITECTURE.md`、`knowledge/DATA_AND_SECURITY.md`、`knowledge/OPERATIONS.md`、`knowledge/QUALITY.md`，并重新生成知识快照与语义索引。

## 验证证据与边界

已完成或已有当前仓库证据：

- Agent Service 全量回归：本轮 137/137 通过。
- Agent 图谱聚焦回归：11/11 通过。
- Agent V5 可观测性评测：8 项检查 100%，p95 约 59.55 ms；V6、PRD、Knowledge Lifecycle 均通过。
- Media Service 受支持 Temurin JDK 18.0.2.1：完整 Maven 测试 **113/113 通过**，其中 lease/Workflow 聚焦测试 19/19 通过。
- Web TypeScript/Vite 构建：本轮未改变 Web；既有构建证据通过，发布前仍应重新执行。
- pi-lens 当前会话诊断复核：24 个已诊断文件无剩余问题；此前提示的 54 条 ruff/pyright/ast-grep/LSP 诊断已由自动修复或格式化处理。
- V6、PRD、Knowledge Lifecycle：既有固定黄金集门禁通过；通用检索或治理变更后应重新执行相关门禁。
- 知识生成与漂移：`python scripts/update_knowledge.py` 和 `python scripts/update_knowledge.py --check` 已通过。
- 当前 JDK 25 的 Mockito inline/ByteBuddy 加载失败是工具链不兼容；仓库声明的有效质量结论使用 JDK 18，不能将 JDK 25 失败解释为产品通过或产品回归。
- `scripts/local_acceptance.py` 已在 localhost-only 范围通过 33/33 检查，覆盖媒体→Agent outbox、时间证据、分析恢复、个人/团队隔离、审批、知识生命周期、工单、VIEWER 只读和缓存安全边界；测试视频包含合法 MP4 `ftyp` 头，避免把真实上传校验绕成任意字节；真实 Docker、中间件、外部模型、正式 IdP 和生产数据库/灾备仍需目标环境证据。

## 建议的发布路线

### Gate 0：继续保持试点

保留 local/mock 模式和现有闭集门禁；补齐 lease、tenant 去重、图谱 team scope 回归；禁止对外承诺生产 SLA、模型准确率或客户 ROI。

### Gate 1：真实集成预发布

选定 IdP、数据库、对象存储、消息系统和模型供应商；完成版本化迁移、最小权限、密钥轮换、真实 JWT owner/team 隔离、outbox 故障注入、worker 重启、对象存储失败、模型超时和备份恢复演练。

### Gate 2：小流量生产试点

设定并批准租户/文件/并发/QPS/成本上限；启用 OTEL、告警、审计和人工审批；使用脱敏 holdout 评估拒答、引用和 LLM 成本；预先定义 rollback、RPO/RTO 和数据删除请求流程。

### Gate 3：扩大规模

只有当真实指标证明 SQLite、同步 worker、本地缓存或当前索引成为瓶颈，才分别迁移 PostgreSQL、持久化工作流、向量索引和分布式缓存。每次迁移保留当前确定性基线做行为对照。

## 参考的开源先例

本次评估核对了以下公开文档/先例，并将其作为设计参考而不是代码复制来源：

- Transactional Outbox：<https://microservices.io/patterns/data/transactional-outbox.html>
- Spring Data JPA locking：<https://docs.spring.io/spring-data/jpa/reference/jpa/locking.html>
- Spring Boot database initialization / Flyway / Liquibase：<https://docs.spring.io/spring-boot/how-to/data-initialization.html>
- Temporal workflow message passing / Signals：<https://docs.temporal.io/encyclopedia/workflow-message-passing>
- OpenTelemetry general semantic conventions：<https://opentelemetry.io/docs/specs/semconv/general/>
- Qdrant payload filtering：<https://qdrant.tech/documentation/concepts/filtering/>

这些先例支持的共同原则是：数据库与出站消息分离但要求消费者幂等；并发写入必须有明确的锁/条件更新；迁移应由单一版本化工具负责；长工作流要能接收外部信号并恢复；向量召回必须和业务 metadata 过滤组合。当前仓库采用了其中的最小、可验证部分，尚未宣称完成其全部生产实现。
