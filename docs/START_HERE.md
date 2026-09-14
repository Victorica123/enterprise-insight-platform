# Enterprise Insight Platform：10 分钟项目地图

这不是两个 Demo 的拼接，而是一条完整的企业洞察工作流：

> 视频/文档 → 授权证据 → RAG 问答与时间戳回放 → 六阶段分析 → PRD 审批 → 知识沉淀/替代/撤回 → 工单审批。

第一次接触项目时，不要从目录逐个阅读，也不要先打开生成向量或历史归档。按下面的入口理解即可。

## 先读什么

1. `README.md`：90 秒理解产品、架构与启动方式。
2. 本文：建立代码地图，知道一个需求应该改哪里。
3. `docs/DEMO_SCRIPT.md`：按用户视角走完 8 分钟主链路。
4. `knowledge/TECHNICAL_IMPLEMENTATION.md`：准备讲解实现细节时再读。
5. `knowledge/QUALITY.md`：面试官追问“如何证明”时查验证证据。

架构优化阶段 0–4 已完成；接手时读 `docs/ARCHITECTURE_OPTIMIZATION_PLAN.md` 的当前状态、[ADR-0016](../knowledge/decisions/0016-bounded-conversations-and-sse.md)、[ADR-0017](../knowledge/decisions/0017-settings-schema-and-domain-boundaries.md) 和 [ADR-0018](../knowledge/decisions/0018-media-migrations-stages-and-web-queries.md)。启动 harness 的 `brief` 读取当前知识入口与 Git 状态，不再加载历史归档；`verify` 运行 Agent/Web/维护服务门禁，平台级验证另按维护规范执行。最新测试和真实中间件范围以 `knowledge/QUALITY.md` 为准。

如果只是修一个明确问题，读完本文后直接进入对应模块，不需要通读全部知识文档。

面试准备只保留两个入口：[讲解与答辩](INTERVIEW_GUIDE.md) 解释框架取舍、召回、通信、故障、幻觉和评测；[演示与计时](DEMO_SCRIPT.md) 维护实际操作。原演练与压力评审已合并；实现事实和质量证据仍分别由 knowledge 文档维护。

2026-09-13 追加了 [Nexus 参考站复核](NEXUS_REFERENCE_AUDIT.md)：当前公开目录 88 页，本轮补齐检索排名、通道过滤/隔离、观测和证据追问。检索策略与边界见 [ADR-0019](../knowledge/decisions/0019-retrieval-ranking-and-channel-isolation.md)，当前部署看 `knowledge/OPERATIONS.md`。

## 只记住三个边界

| 边界 | 谁负责 | 不能做什么 |
| --- | --- | --- |
| 媒体生命周期 | Spring Media Service | Agent Service 不接管上传、转写和播放授权 |
| 知识与分析生命周期 | FastAPI Agent Service | Media Service 不决定 RAG、PRD 或知识治理状态 |
| 用户交互 | React Web | 前端隐藏按钮不等于鉴权，权限必须由后端验证 |

两个后端共享受信 JWT、`tenant_id` 和 `owner_id` 语义；团队读取按 tenant 共享，个人读取按 tenant + owner 隔离。

## 一张代码地图

### Media Service

| 要找的问题 | 入口 |
| --- | --- |
| 登录、JWT、Workspace、成员角色 | `services/media-service/.../auth/` |
| 上传、分片、播放与清理 | `services/media-service/.../media/` |
| 媒体任务状态、配额、租约与完成 | `workflow/VideoTaskService`、`TaskQuotaService`、`TaskLeaseService`、`TaskCompletionService` |
| 阶段执行与分页查询 | `workflow/TaskStageLogService`、`TaskStageObserver`、`WorkflowController` |
| 转写完成跨服务投递与熔断 | `integration/AgentOutboxDispatcher`、`AgentDeliveryCircuit` |
| 配置绑定与 H2/MySQL 升级 | `config/AppConfiguration`、`MediaMigrationConfiguration`、`LegacyMediaSchema`；`src/main/resources/db/migration/` |

### Agent Service

新增业务入口统一位于 `services/agent-service/app/architecture/`；它们组合下表中的实现模块，并保留旧导入路径供兼容测试使用。优先按全景层选择 façade：`orchestration.py`（对话）、`retrieval.py`（检索与证据）、`execution.py`（三层执行器）、`knowledge.py`（知识底座）、`governance.py`（审批与生命周期）、`observability.py`（观测与审计）。完整映射见 [ARCHITECTURE_PANORAMA.md](ARCHITECTURE_PANORAMA.md)。

| 要找的问题 | 入口 | 职责 |
| --- | --- | --- |
| 文档/chunk/摄取回执 | `database.py` | 核心知识持久化，不含聊天观测逻辑 |
| 配置与旧库升级 | `config.py`、`schema/` | Settings 校验、编号迁移、ledger 与启动锁 |
| JSON/SSE 会话 | `architecture/conversation.py`、`chat_service.py`、`chat_events.py` | 共用授权流水线、有界队列、最终审核与取消 |
| 主题记忆与会话预算 | `conversation_memory.py`、`conversation_store.py`、`conversation_lease.py` | 窗口/摘要提示、租约续期、预留退还与失效 fencing |
| 问答指标、日志、反馈、历史引用 | `chat_observability_store.py` | 观测数据与回放 |
| 标准/Agentic RAG | `rag.py`、`agentic_rag.py` | 工作流编排与回答 |
| 授权检索和缓存 | `retrievers.py`、`retrieval_execution.py`、`chunk_index.py`、`text.py`、`embeddings.py` | scope 前置、最终排名、通道阈值/截止/容量与缓存 |
| 主题路由与相邻块 | `topic_routing.py`、`evidence_sources.py` | 授权候选澄清、主题过滤、预算内章节扩展 |
| 向量存储与维护 | `vector_codec.py`、`embedding_maintenance.py` | 二进制/JSON 兼容、有界后台补齐 |
| 六阶段分析 | `analysis_evidence.py`、`analysis_pipeline.py`、`analysis_store.py` | 冻结证据、阶段执行与恢复 |
| PRD 发布和派生交付物 | `publication_service.py`、`publication_artifacts.py` | 审批状态与交付物投影 |
| 知识版本与替代/撤回 | `knowledge_lifecycle_store.py` | 版本物化、CAS 与原子回滚 |
| 图谱抽取规则 | `graph_extraction.py` | 纯文本到实体/关系，不访问数据库 |
| 图谱存储和重建 | `graph_store.py`、`graph_algorithms.py`、`graph_rag.py` | 持久化、纯算法、失效和查询 |
| 工单与待审批动作 | `ticket_store.py`、`ticket_domain.py` | 状态 CAS、审批与纯规则 |
| 受控工具执行 | `tools.py` | 工具注册、策略校验与执行编排 |
| 工具审计与指标 | `tool_observability_store.py` | 调用日志、状态统计与时延指标 |

### React Web

`apps/web/src/api.ts` 是兼容入口；新增代码应优先进入领域模块：

- 通用请求/JWT：`apiClient.ts`
- 会话/SSE：`chatApi.ts`、`hooks/useConversation.ts`、`features/qa/`
- Router/Query/身份边界：`App.tsx`、`queryClient.ts`、`workspaceContext.ts`、`hooks/useWorkspaceSession.ts`
- 页面数据与状态：`hooks/useQAWorkspace.ts`、`useKnowledgeWorkspace.ts`、`useAnalysisData.ts`、`useMediaWorkspace.ts`、`useTicketsWorkspace.ts`
- 文档与 Embedding：`knowledgeApi.ts`
- 分析与发布：`analysisApi.ts`
- 媒体：`mediaApi.ts`
- 图谱：`graphApi.ts`
- 工单与审批：`ticketApi.ts`
- 监控、日志与反馈：`observabilityApi.ts`
- 页面：`features/`

## 按症状定位

| 症状 | 先看 | 最小验证 |
| --- | --- | --- |
| 上传或转写不推进 | Media `workflow/`、`integration/` | 对应 Maven 测试 |
| 问答召回错误或越权 | `retrievers.py`、`database.py` | RAG 测试 + V6 |
| 连续追问串题、断流或租约冲突 | `chat_service.py`、`conversation_*`、`evidence_sources.py` | conversation stream tests + Conversation V1；改证据时加 V6 |
| 启动配置或旧库升级失败 | `config.py`、`schema/` | Settings + schema startup tests |
| 分析等待后结果漂移 | `analysis_evidence.py`、`analysis_store.py` | analysis workflow + PRD eval |
| 知识撤回后仍被召回 | `knowledge_lifecycle_store.py`、`retrievers.py` | lifecycle eval + localhost smoke |
| 图谱残留失效知识 | `graph_store.py` | graph tests + lifecycle eval |
| 监控数据或历史引用异常 | `chat_observability_store.py` | metrics/observability tests |
| 工具调用审计或指标异常 | `tool_observability_store.py` | V3 tools + tenant isolation |
| 页面类型或请求错误 | 对应 `*Api.ts` 与 `features/` | `npm run build` |

## 哪些内容不要先读

- `docs/archive/`：迁移历史，只用于追溯，不代表当前实现。
- `knowledge/generated/SEMANTIC_INDEX.json`：机器向量索引，禁止人工阅读或编辑。
- `runtime/`、SQLite、日志和上传文件：运行数据，不是代码事实。
- `evaluate_v2.py`～`evaluate_v5.py`：历史评测演进；当前合并门禁以 V6、PRD V1、Knowledge Lifecycle V1 和 Conversation V1 为主，V5 用于观测回归。

## 完成修改前

至少运行改动模块的聚焦测试、对应的 lint（Python：`ruff check --config ruff.toml services/agent-service scripts quality`；Web：`npm run lint`）、`python scripts/update_knowledge.py --check`，再按 `skills/enterprise-insight-maintainer/references/maintenance-workflow.md` 判断是否需要服务级或平台级验证。不要为了减少文件数把身份、审批、证据、契约或质量门禁重新揉回一个大文件。
