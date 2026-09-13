# 架构与工作逻辑优化：方案、功能拆分与前后对比（对标 Nexus Agent）

> 日期：2026-09-11 立项，2026-09-12 三批落地，2026-09-13 完成接手范围与验证
> 性质：第一至七节是架构评审与分阶段计划；第八节是落地记录；第九节是项目功能拆分（优化动了哪一块）；第十节是优化前后的量化对比与如何取舍 Nexus 做法  
> 参照物：Nexus Agent 公开文档（javaup.chat/super-agent，概览 7 页全文可读，25 页细节被付费墙截断，仅能读到设计意图与参数，读不到完整源码）  
> 评审对象：当前仓库 `services/agent-service`、`services/media-service`、`apps/web`

## 当前状态（2026-09-13）

阶段 0–4 已按批准的项目边界完成并验证。阶段 4 补齐 Media 职责与配置拆分、Flyway、真实阶段日志、Agent 投递熔断，以及 Web 路由、查询缓存、请求取消和 feature 状态下沉。Agent **244/244**、Web **21/21**、Media **150/150**；H2/SQLite 与真实 MySQL/Redis/RocketMQ/MinIO 纵向验收均为 **42/42**。Conversation V1 **9/9**，其余门禁、MySQL 迁移/备份恢复、断连恢复和有限 k6 证据见第十一节与 `knowledge/QUALITY.md`。未提交或部署现有服务。

第一至四节保留 **2026-09-11 原始评审快照**，“现状/缺少”指立项时；第十节保留 **2026-09-12 历史提交对比**，不代表本轮新增改造的性能收益。当前完成项看第五、八、九、十一节。

## 一、结论（立项时）

功能闭环已经成立，问题集中在三处：

1. **工作逻辑是"if/else 分流"，不是"编排产物 + 执行器"。** `workflow_mode` 由前端直接指定，服务端没有执行计划这一层契约；意图判定、工具直达、检索规划散落在 `agentic_rag.py` 的函数调用顺序里，无法单独测试、跳过或替换。
2. **检索链路每请求做全量重算。** 关键词检索对作用域内每个 chunk 重新分词、重算 n-gram；向量以 JSON 文本存储，每次缓存失效后整表解析；hybrid 的两路串行执行。语料小时看不出来，chunk 上万后会线性恶化。
3. **横切能力缺位。** 没有会话记忆、没有流式输出、trace 没有阶段耗时、模型与工具调用没有单次上限、配置读取散落 47 处、DDL 分布在 7 个文件。

Nexus Agent 值得借鉴的核心是一句话：**确定性编排先做决策，执行器只负责执行，每一步都有产物、预算、耗时和上限。** 它的中间件堆栈（Neo4j、PGVector、ES、Kafka）不是重点，也不建议现在引入。

## 二、Nexus Agent 的做法与本项目现状对照

| 维度 | Nexus Agent 做法 | 本项目现状（代码证据） | 差距判断 |
| --- | --- | --- | --- |
| 编排产物 | 前置编排器五步链（路由、改写、歧义检测、子问题拆分、知识域收缩）产出结构化 `ExecutionPlan`，含 `executionMode / rewrittenQuestion / subQuestions / knowledgeDomains / clarifyQuestion` | `ConversationOrchestrator.answer()` 只按 `workflow_mode` 二选一（`architecture/orchestration.py:45`）；路由、规划、工具直达判断在 `agentic_rag.py:110-130` 顺序调用，没有计划对象 | 缺一层契约 |
| 执行器分发 | `ExecutionMode` 枚举 + `ConversationExecutorRegistry.get(mode)`，新增模式只加一个 Bean | standard / agentic 两个函数硬编码注入；工具直达是 agentic 内部的分支 | 缺注册表 |
| 澄清优先 | 判断顺序：歧义澄清 > 知识问答 > 开放 Agent | 无澄清执行器；证据不足时直接拒答（`rag.py:check_evidence`） | 缺 |
| 证据预算 | 单子问题 2200 字符、总预算 5200 字符、单父块 2200 字符；向量最低相似度 0.45；关键词相对阈值 0.35 | 只有 `MAX_SOURCES = 4` 按条数截断（`rag.py:26`），无字符预算；门控用覆盖率分 | 缺字符预算 |
| Parent-Child 块 | 检索命中 child 小块，回答阶段聚合到 parent 大块 | `split_text` 已有标题层级链（`rag.py:120-160`），但只存 `chunk_title`，没有 parent 标识和聚合 | 半成品 |
| 会话记忆 | 无记忆 / 滑动窗口 / 摘要压缩三策略；最近 4 轮原文保留，单次摘要最多推进 6 轮，原文窗口 2200 字符，摘要 1400 字符 | `ChatRequest` 无 `conversation_id`、无历史（`models.py:149-167`）；每轮独立 | 缺 |
| 流式输出 | SSE：thinking → 正文分片 → 引用 → 推荐追问 → 结束，支持停止 | `/chat` 同步返回整包 JSON；仓库内无 `StreamingResponse` | 缺 |
| Agent 安全上限 | 单次模型调用 8 次、工具调用 6 次，会话累计 40 / 30；工具重试 2 次、退避 200–1200ms | 检索轮次上限 2（`MAX_RETRIEVAL_ROUNDS`）；LLM 调用次数无计数；SDK 层有 `max_retries`，工具层无重试 | 部分 |
| 全链路耗时 | AOP 记录每阶段耗时与决策结果，观测面板按阶段展示 | `TraceStep` 只有 `name / status / detail`（`models.py:202`），只在路由层记整体 `latency_ms` | 缺阶段耗时 |
| 并发模型 | WebFlux `Flux.defer` 延迟启动，阻塞编排切到 `boundedElastic`；Redis 租约 + JVM 任务注册两级互斥 | 50 个路由中 49 个是同步 `def`，靠 anyio 线程池（默认 40 线程）承载阻塞 LLM 调用；Dockerfile 单 worker | 可接受，但需显式化 |
| 文档流水线 | Kafka 异步、阶段化任务日志、策略推荐 | 文档上传同步入库（`rag.ingest_document`，一个事务完成切块、向量、图谱）；媒体侧有 outbox 但无阶段日志 | 小文件可接受 |
| 扩展点 | `RetrievalChannel` 接口、切块策略接口、记忆策略接口、Tool 注册、MCP、SKILL.md | `Retriever` Protocol 已存在（`retrievers.py:84`）；`register_tool` 已存在（`tools.py:78`）；无切块策略与记忆策略接口 | 部分 |
| 职责边界 | "Python 出能力，Java 做决策"，Python 返回候选与打分，Java 校验后才用 | 本项目正相反：Agent Service（Python）拥有决策与治理，Media（Java）拥有媒体生命周期。边界清晰，且模型输出一律经校验（ADR-0012） | 不需要改 |

Nexus 公开页面里可以直接拿来用的几个具体机制：

- **相对置信度而非绝对分**：知识路由置信度 `confidence = top1 / max(10, top1 + top2 + 5)`，只看 top1 对 top2 的领先程度，跨库可比；阈值 0.55。
- **五条澄清条件**（任一成立即澄清，单候选直接放行）：候选为空；路由结果无文档；置信度低于 0.55；候选至少 2 个、分差不超过 3 且两者属于不同知识域。
- **按通道分别门控，再按名次融合**：向量通道用最小相似度、关键词通道用相对分数下限过滤弱命中，然后才做 RRF（K=60），原始分和元数据只做微调。本项目现在是先融合再用加权分门控，顺序相反。
- **阶段化 trace**：`startStage / completeStage(metadata) / failStage` 三个句柄落表，观测面板按阶段展示耗时与决策结果；另有检索观测、通道执行记录、阶段基准三个查询接口。
- **SSE 事件信封**：`{type, content, timestamp, conversationId, exchangeId}`，类型 `thinking / text / reference / recommend / status / error`，顺序 thinking → text* → reference → recommend → 结束。
- **Prompt 外置**：所有提示词放 `classpath:prompt/*.st` 模板并缓存，代码里不含提示词字面量。本项目提示词在 `llm.py`、`llm_router.py` 内联（2026-09-12 已外置到 `app/prompts/*.txt`）。
- **影子路由**：用户手选文档时后台静默跑一遍自动路由并落库对比，零打扰地得到路由命中率。本项目可对 `workflow_mode` 做同样的事：用户指定模式时静默跑一遍 `decide_mode`，记录两者是否一致（2026-09-12 已落地为 `shadow_decision` 与 `chat_metrics.mode_agreement`）。
- **精排失败不伪造分数**：rerank 不可用时回退融合榜并在观测数据中标明，而不是静默降级。`retrievers.py:_rerank_head` 返回 `None` 时目前没有写 trace。

本项目**优于** Nexus 公开版的部分，改造时必须保住：检索前的 tenant/owner 授权范围（`RetrievalScope`）、PRD / 知识 / 工具的人工审批与审计、outbox claim lease 与 fencing、契约文件与 ADR、闭集评测门禁。

## 三、当前代码的量化体检

Agent Service（`services/agent-service/app`，约 13.2k 行）：

| 指标 | 数值 | 含义 |
| --- | --- | --- |
| 路由处理函数 / 其中 async | 50 / 1 | 阻塞工作全部落在线程池 |
| `os.getenv` 调用点 / 涉及文件 | 47 / 12 | 配置无单一入口，无法一次校验 |
| `with connect()` 调用点 | 67 | 每次调用开关一个 SQLite 连接 |
| `init_db()` 调用点 | 18 | 每次读写前都进 memo 判断，逻辑上多余 |
| `create table` 出现的文件数 | 7 | DDL 分散在 database / graph_store / ticket_store / publication_artifacts / analysis_store / knowledge_lifecycle_store / db_compat |
| 路由导入 façade / 直接导入实现模块 | 8 / 24 | ADR-0015 的 façade 只覆盖了三分之一的调用 |
| 重复工具函数 | `deduplicate_preserve_order` 在 `rag.py:358` 和 `retrievers.py:424` 各一份 | 小事，但说明缺公共文本模块；2026-09-12 已收敛到 `app/text.py` |
| 最大模块 | `graph_store.py` 849 行、`agentic_rag.py` 781 行、`database.py` 703 行、`ticket_store.py` 699 行、`rag.py` 695 行 | 单文件承担存储 + 算法 + 编排 |

检索热路径（`retrievers.py`）：

- `load_chunks()` 把作用域内全部 chunk 载入内存，按 `(db, revision, tenant, owner, asset_ids)` 做 64 项 LRU；任何一次写入 bump revision 后所有作用域全部失效并整表重载（含 JSON 解析两套向量）。
- `KeywordRetriever.search()` 对每个 chunk 每次请求调用 `extract_search_terms(searchable)`，重新做归一化和 1/2-gram，没有倒排索引，也没有把词项集缓存到 chunk 对象上。
- `HybridRetriever.search()` 先跑 keyword 再跑 embedding，两路串行；两路各自 `load_chunks()` 一次（命中缓存后代价小，但缓存未命中时是两次整表读）。
- `EmbeddingRetriever._search_real()` 对缺 `embedding_v2` 的 chunk 在请求路径上现场推理，首个请求会承担整批 embedding 延迟。

Media Service（`services/media-service`，约 7.9k 行 Java）：

- 处理线程池 core 2 / max 4 / queue 50（`config/AsyncConfig.java:15-17`）；单节点最多 4 条媒体任务并行，超过后排队 50 条再拒绝。
- 6 个 `@Scheduled` 调度器：workflow dispatch 250ms、agent outbox 2s、reaper 60s、cleanup 10min、retention 1h。
- `VideoTaskService` 459 行、约 30 个公开方法，同时承担配额、lease、CAS 完成、内容去重 fan-out；`AppProperties` 635 行是所有配置的单点。
- `ddl-auto: update`（`application.yml:45`）仍是开发期策略；63 处 `@Transactional`，20 处条件装配。
- Agent 调用 `HttpClient` 连接超时 3s、请求超时 15s（`AgentTranscriptClient.java:21,41`）；无熔断。

Web（`apps/web`，约 3.6k 行）：

- 运行时依赖只有 react、react-dom、lucide-react；无路由库、无数据请求库。
- `main.tsx` 持有 29 个 `useState`；`QAView.tsx` 474 行；媒体列表用固定 2s `setInterval` 轮询（`hooks/useMediaWorkspace.ts`）。
- 请求统一走 `apiClient.ts` 的 `safeFetch`，鉴权头集中处理，这一点是对的。

## 四、目标架构（Agent Service）

```text
POST /chat  /chat/stream
   │
   ▼
RequestContext（已有：principal → scope）
   │
   ▼
PreparationChain            ← 新增，可插拔步骤列表，每步只改 ExecutionPlan
   ├─ load_memory            会话记忆（none / window / summary）
   ├─ rewrite_question       结合历史做指代补全（规则优先，LLM 可选）
   ├─ classify_intent        复用 llm_route_question / detect_intents
   ├─ split_subquestions     复用 split_complex_question，上限 4
   ├─ narrow_scope           tenant/owner/asset + 知识域（来源类型、文档标签）
   └─ decide_mode            CLARIFY > TOOL_ONLY > RETRIEVAL > AGENTIC
   │
   ▼
ExecutionPlan（frozen dataclass，写入 trace，可回放）
   │
   ▼
ExecutorRegistry.get(plan.mode).execute(ctx, plan)   ← 新增注册表
   ├─ ClarificationExecutor   直接返回澄清问题，不检索不调模型
   ├─ ToolOnlyExecutor        现有 build_tool_only_answer 路径
   ├─ RetrievalExecutor       现有 rag.answer_question
   └─ AgenticExecutor         现有 agentic_rag（多轮检索 + 图谱 + 工具 + 引用审核）
   │
   ▼
EvidenceBudget → build_answer → review_citations → follow-up 建议
   │
   ▼
StreamEmitter（SSE）/ ChatResponse（JSON）
   │
   ▼
memory.append_turn + record_chat_metric（含阶段耗时）
```

原则：façade（`app.architecture.*`）是唯一入口；`rag.py`、`agentic_rag.py` 降级为执行器实现，不再被路由直接导入。

## 五、分阶段改造计划

每个阶段以 Agent 全量 unittest、V6 / PRD / Knowledge Lifecycle / Conversation 相关评测、共享 lint 和知识漂移检查为退出条件；跨平台改动另跑 Media、Web 与 localhost 验收。阶段内不改 HTTP 契约字段的删除，只做新增。

### 阶段 0：工作逻辑显式化（优先级最高，约 1–2 周）

| # | 改动 | 涉及文件 | 验证 |
| --- | --- | --- | --- |
| 0.1（已落地 2026-09-12） | 新增 `ExecutionPlan` 与 `PreparationChain`，把 `route_question`、`plan_retrieval`、`_is_tool_only_question` 改写成链上的步骤 | 新增 `app/architecture/planning.py`；改 `orchestration.py` | `test_architecture_boundaries.py` 增加"计划可序列化、步骤可单独跳过"用例 |
| 0.2（已落地 2026-09-12） | 新增 `ExecutorRegistry` 与 `ClarificationExecutor`；`workflow_mode` 保留为向后兼容输入，服务端最终以 `plan.mode` 为准 | `orchestration.py`、`models.py`（`AgentSummary` 增加 `execution_mode`、`clarify_question`） | 现有 158 个用例不变；新增澄清用例 |
| 0.3（已落地 2026-09-12） | `TraceStep` 增加 `duration_ms`，每个阶段用 `perf_counter` 计时；`chat_logs.trace_json` 自然携带 | `models.py`、各执行器 | V5 观测评测保持 8/8 |
| 0.4（已落地） | `call_limits.py` 以 ContextVar 绑定每请求模型 8 / 工具 6 上限；会话模式另有累计预留与退还 | `call_limits.py`、`chat_service.py`、`llm_client.py`、`tools.py` | 请求与会话预算回归 |
| 0.5（已落地 2026-09-12） | 证据字符预算：单来源 ≤ 2200、总量 ≤ 5200，先按分数取，再按预算裁 | `rag.py` 抽出 `evidence_budget.py` | V6 三种模式 decision / recall@3 / fact 不下降 |
| 0.6（已落地 2026-09-13） | 已授权客户/项目候选相对置信度与澄清；明确主题/比较不误拦，无候选走原拒答；精排降级可见 | `topic_routing.py`、`planning.py`、`retrievers.py` | 授权候选、指代歧义及降级回归 |
| 0.7（已落地 2026-09-12） | Prompt 外置到 `app/prompts/*.txt`（或 Jinja 模板）并缓存，`llm.py`、`llm_router.py` 只做变量填充 | `llm.py`、`llm_router.py`、新增 `app/prompts/` | 现有 LLM 路由用例不变 |
| 0.8（已落地 2026-09-12） | 影子路由：用户显式传 `workflow_mode` 时，后台仍跑 `decide_mode` 并把"系统会选什么 / 用户选了什么 / 是否一致"写入 `chat_metrics` | `orchestration.py`、`chat_observability_store.py` | 监控面板新增一致率 |

### 阶段 1：检索效率（约 1 周）

| # | 改动 | 收益 |
| --- | --- | --- |
| 1.1（已落地 2026-09-12） | 索引时预计算 chunk 词项集并随缓存对象存放（`Chunk.terms: frozenset`），关键词检索不再每请求重新分词 | 关键词路径从 O(N·L) 降到 O(N·|q|) |
| 1.2（已落地 2026-09-12） | 在缓存项内附带按词项的倒排 `dict[str, list[int]]`，查询只碰命中 posting | 大语料下接近 O(命中数) |
| 1.3（已落地 2026-09-13） | 带版本头的 float32 blob，旧 JSON 双写/读取回退 | 已验证兼容与损坏回退；新性能收益未测 |
| 1.4（已落地 2026-09-12） | Hybrid 两路共用授权快照并行检索 | 历史基准见 10.3，不外推固定倍数 |
| 1.5（已落地 2026-09-13） | 默认 64 条后台补齐，推理不持写事务；请求缺向量时整批 hash 降级 | 首请求不补算文档向量 |
| 1.6（已落地 2026-09-12） | 缓存失效粒度改为按 tenant 的 revision（`system_meta` 增加 `content_revision:<tenant>`），一个租户写入不再清空所有租户缓存 | 多租户下缓存命中率 |
| 1.7（已落地 2026-09-13） | 同文档同标题链的授权相邻块在预算内合并；主题过滤贯穿扩展，视频不合并 | 保留 parent_key / chunk_indices 与时间证据 |

### 阶段 2：会话与流式（约 1–2 周）

| # | 改动 |
| --- | --- |
| 2.1（已落地） | 会话/轮次持久化，none/window/summary；最近四轮 2200 字符、摘要 1400 字符、单次最多推进六轮；累计预算 40/30 与可续租 CAS |
| 2.2（已落地，受限规则） | 从已授权用户问题补全客户/项目字面标识；模型仅用于受约束摘要，历史答案不是证据，比较后的歧义不绑定最后一个主题 |
| 2.3（已落地） | `/chat/stream` 发送 plan/stage/delta/sources/follow_up/done/error；事件 sink 连接成熟执行器，JSON/SSE 共用 chat_service，最终 done 经过引用审核 |
| 2.4（已落地） | AsyncOpenAI 答案流、64 项队列、15 秒心跳、整体时限和取消；同步阶段共用 anyio 线程池，本地模板完成后分片 |
| 2.5（已落地） | Web fetch/ReadableStream，连续追问、停止、新建、最终引用与建议；Workspace 切换/登出清理，generation 阻止迟到回写 |

### 阶段 3：结构收敛（可与前两阶段并行）

| # | 改动 |
| --- | --- |
| 3.1（已落地） | 不可变 Settings、类型解析、启动校验和环境快照缓存；仅 config.py 读取业务环境变量，保留旧 getter |
| 3.2（已落地） | schema 编号迁移与 ledger、统一 init_db；SQLite 写事务/进程锁、MySQL advisory lock/可重试步骤，拒绝未知版本；未引入 Alembic，真实 MySQL 待验证 |
| 3.3（已落地） | routes 业务依赖只经 architecture；auth/models/analysis_models/config 为基础例外；静态回归检查边界 |
| 3.4（已落地） | 分词、n-gram、停用词、顺序去重统一在 text.py，保留旧导入兼容 |
| 3.5（已落地） | graph_algorithms 与 ticket_domain 分离纯算法/规则，各 store 保留事务与兼容导出 |
| 3.6（已落地） | app.serve 默认一个 worker，可显式配置；anyio 默认 40、specialist 默认 4；缓存按 revision 失效，扩进程前量测内存与负载 |

### 阶段 4：Media 与 Web（2026-09-13 已完成）

Media 已拆分 quota/lease/completion 和 12 个配置组，加入 H2/MySQL Flyway V1/V2、冻结 V1 的旧库接管校验、可查询阶段记录和 Agent 投递熔断。Web 使用 HashRouter 和 TanStack Query，按身份/Workspace/角色隔离缓存、贯穿 AbortSignal，main 状态下沉至 feature controller。真实 MySQL 验收修复 ENUM 元数据、Agent 长文本列和监控 SQL 别名问题；新增 Agent 第八项迁移，既有迁移不重写。前端 viewer 写入口补齐禁用，四眼审批保持原语义。决策见 [ADR-0018](../knowledge/decisions/0018-media-migrations-stages-and-web-queries.md)。

- Media：`VideoTaskService` 拆为 `TaskQuotaService` / `TaskLeaseService` / `TaskCompletionService`；`AppProperties` 保留兼容聚合，12 组 `@ConfigurationProperties` 独立绑定；Flyway 管理迁移，Hibernate 仅 validate。阶段表只记录实际执行的读取、抽音频、转写、摘要、复用、提交和投递；mock 不记录未执行的抽音频，不虚构转码。客户端单次 HTTP 发送，outbox 持久退避，熔断期间不消耗 attempt。
- Web：引入 `react-router` 与 `@tanstack/react-query`（轮询带退避与 `AbortController`），把 `main.tsx` 的 29 个状态下沉到各 feature；`QAView` 拆成 `QuestionForm` / `AnswerStream` / `SourceList` / `TracePanel`。

## 六、明确不做的事

- 不引入 Neo4j、PGVector、Elasticsearch、Kafka。`docs/ARCHITECTURE_PANORAMA.md` 已约定：只有真实指标证明 SQLite 扫描或本地缓存成为瓶颈才迁移。
- 不把确定性 specialist 改成无界自治 Agent。
- 不改变 Media / Agent 两服务边界，不新增共享表。
- 不删除 `workflow_mode` 等既有契约字段，只新增。

## 七、建议的起手顺序

先做 0.1 + 0.2 + 0.3（执行计划、注册表、阶段耗时），因为它们不改算法、不改数据，只重排现有函数，风险最低，且之后所有阶段都挂在这层契约上。随后做 1.1 + 1.4（词项预计算、两路并行），这是最直接的效率收益。会话记忆和 SSE 放在第三步，因为它们要动契约和前端。

## 八、落地记录

- 2026-09-13（阶段 4 最终收尾）：Media **150/150**、Agent **244/244**、Web **21/21**，lint 零 error、Web 构建通过。两种环境各 **42/42** 验收；真实 MySQL 迁移专项 6 项、分片/对象存储 4 项、Agent 断连恢复 3 项、备份恢复 3 项通过。浏览器验证六路由、宽窄屏、QA 会话保留与停止、Workspace/角色清理和只读入口；k6 3 VUs/150 请求零失败，限于本机小样本。现有用户服务保持原状，原迁移来源未改动。最新口径见第十一节。
- 2026-09-13（接手收尾）：阶段 2 会话/SSE 与阶段 3 配置、编号迁移、领域边界和运行并发配置完成，QA 组件拆分完成。新增 ADR-0016/0017，修正 AGENTS 的失效 Skill 路径与读取归档的启动 harness。最终 Agent **241/241**、Web **13/13**、Media **135/135**、localhost **36/36**；V6、PRD、Knowledge Lifecycle、V5 通过，Conversation V1 **9/9**。浏览器验证真实 JWT 注册/文档上传、连续追问、新建、宽窄屏和 Workspace 清理；临时 SQLite 备份校验及恢复通过。详情见第十一节。
- 收尾回归发现并修复：显式换客户时来源混入、比较后指代错误、模型摘要虚构主题、相邻块重新引入已排除客户、租约失效误报 500，以及问答页面样式依赖其他懒加载页面。失败样例已纳入回归；未切换模型、未改两服务边界。


- 2026-09-13（Codex 接手）：从 Claude 原始会话及项目记忆恢复授权范围，以干净工作树 `40c2093` 和实跑 Agent **199/199** 为起点。第一批补齐 1.3 的可回退二进制向量双写/读取、1.5 的有界后台补齐、1.7 的同文档同章节相邻块合并；0.6 使用已授权客户/项目候选的相对置信度，明确主题和跨主题比较不误拦，空知识库仍走原拒答路径。新增 10 个回归后 Agent **209/209**；V6 hybrid 98%/97%/97%、PRD 12/12、Knowledge Lifecycle、V5 均通过。当时继续阶段 2 会话记忆与 SSE；不修改模型选择，不引入额外中间件。原有三批和对比数字仍按历史基线保留。

- 2026-09-12：阶段 1 的 1.1、1.2、1.4、1.6 与 0.6 中“精排降级可见”部分落地。新增 `app/text.py`（唯一分词器与 CJK 窗口 / 锚点函数）和 `app/chunk_index.py`（授权 chunk 快照、预计算词项、词项倒排、按租户 revision 缓存）；`retrievers.py` 只保留检索通道与融合逻辑，并向后兼容地重导出 `Chunk`、`RetrievalScope`、`load_chunks` 等符号，测试与评测脚本无需改动。`embeddings.py`、`rag.py`、`agentic_rag.py` 的重复文本函数收敛到 `app/text.py`。关键词路径的结果顺序与旧的逐块打分实现完全一致，由 `tests/test_chunk_index.py` 用暴力算法逐 query 对照。验证：Agent 170/170、ruff 0 告警、V6 / PRD / Knowledge Lifecycle / V5 四个门禁通过，数字见 `knowledge/QUALITY.md` 的 2026-09-12 条目。实际顺序与第七节建议不同：先做了阶段 1 的低风险效率项，阶段 0 的执行计划 / 执行器注册表 / 阶段耗时（0.1–0.3）是下一步。
- 2026-09-12（同日第二批）：阶段 0 的 0.1、0.2、0.3 落地。新增 `app/architecture/planning.py`（`PlanDraft`、`ExecutionPlan`、`PreparationChain`、`StageTimer`、规则版澄清门与工单直达判定）；`agentic_rag.py` 把 `route_question` / `plan_retrieval` 改写为作用于 `PlanDraft` 的 `classify_intent` / `plan_queries` 两个链步骤，state 版本只是薄包装；`orchestration.py` 改为“链生成计划 → `ExecutorRegistry` 按 `plan.mode` 选执行器”，注册 `RetrievalExecutor`、`AgenticExecutor`、`ToolOnlyExecutor`、`ClarificationExecutor`。`workflow_mode` 保留为输入：standard 请求跳过分类与规划步骤，agentic 请求把计划传给处理器复用，不重复调用路由模型。`TraceStep.duration_ms` 由链和各执行器计时；`AgentSummary` 新增 `execution_mode`、`clarify_question`；`execution_plan` 作为 trace 步骤写入，`chat_logs.trace_json` 自然携带。澄清门当前只拦“无内容锚点”的问题（如“为什么？”），0.6 的相对置信度公式仍待做。验证：Agent 176/176、ruff 0 告警、四个门禁通过，黄金集 42 个问题无一被澄清门或工单门误拦。
- 2026-09-12（同日第三批）：阶段 0 的 0.4、0.5、0.7、0.8 落地。新增 `app/call_limits.py`（`LimitCounter` 以 ContextVar 绑定到请求，模型 8 / 工具 6，`ConversationOrchestrator.run` 在一个预算内完成计划与执行并追加 `call_limits` trace；`llm_client.create_chat_completion` 只在真正出网时消耗预算，`llm_router` 超限退回规则，`rag.build_answer` 超限退回模板，`tools.execute_tool` 超限不执行并记 `limited` 审计）；新增 `app/evidence_budget.py`（单来源 2200 / 总量 5200 字符，先按分数选再按预算裁，句末优先、省略号标记、尾部不足 120 字符即丢弃；单轮与多轮路径都在证据检查前应用，trace 写 `evidence_budget`）；新增 `app/prompts/`（10 个 `.txt` 模板 + `string.Template` 渲染 + 进程内缓存 + `AGENT_PROMPT_DIR` 覆盖，`llm.py` / `llm_router.py` 不再含提示词字面量）；影子路由（`planning.shadow_decision` 规则版，`ExecutionPlan.shadow_mode / shadow_reason / mode_agreement`，`chat_metrics` 三个新列，`/metrics/summary` 五个新字段，监控面板新增“路由一致率”与不一致配对）。`_question_needs_tools` 及其触发词搬到 `planning.py`，旧名字保留。`.env.example` 新增五个变量。`orchestration.answer_chat` 保留，`run_chat` 额外返回计划供指标落库。验证：Agent 199/199（新增 `tests/test_request_budgets.py` 23 个用例）、ruff 0 告警、四个门禁通过（V6 hybrid 98/97/97、PRD 12/12、Knowledge Lifecycle、V5）、Web lint 0 error / 18 warning（与改动前相同）、`npm test` 7/7、生产构建通过。
- 2026-09-12 当时未做的 0.6、1.3/1.5/1.7、阶段 2/3 已在 2026-09-13 补齐；用户继续授权后的阶段 4 也已完成，以上日期记录保留各批次当时的验证数字。
- 2026-09-12（对比基准）：新增 `quality/agent-evals/bench_retrieval.py` 合成语料检索基准，对 `7195dad` 与 `9410ef3` 两棵源码树各跑 2,000 与 5,000 chunk，结果见第十节 10.3；同时用 `git grep` 统计两个提交的结构指标（10.2）。

## 九、项目功能拆分（优化对象的全貌）

本节回答"这个项目到底由哪些功能组成，优化动了哪一块"。功能按服务与入口拆分，最后一列反映截至 2026-09-13 的完成状态。Media 实现保持原有边界；文件与接口数量以生成快照为准。

### 9.1 Media Service（Java 17 / Spring Boot 3.3，150 个测试）

| 功能域 | 包 | 职责 | 关键机制 | 本轮优化 |
| --- | --- | --- | --- | --- |
| 身份与工作区 | `auth/` | 登录、JWT 签发与校验、OIDC 身份核验、登录限流、令牌黑名单、Workspace 创建 / 邀请 / 成员角色 | 本地与 Redis 两套限流和黑名单实现，`WorkspacePrincipal` 携带 tenant / owner / role | 未改 |
| 媒体上传与存储 | `media/` | 单文件、分片、直传三种上传，文件校验，本地 / S3 存储，播放授权，分片清理 | 分片会话在 Redis，播放走签名 URL | 未改 |
| 媒体任务工作流 | `workflow/` | 任务状态机、租约、分布式锁、活跃任务配额、超时回收 | lease + fencing、CAS 完成、实际阶段日志 | quota/lease/completion 拆分，阶段分页/权限回归 |
| 转写与摘要 | `transcript/`、`summary/` | 抽音频、Whisper 转写、LLM 摘要，均有 mock 实现 | OpenAI 兼容客户端，mock 用于本地验收 | 只对实际执行阶段计时与记录，保留模式边界 |
| 跨服务投递 | `integration/` | 转写完成事件写 outbox，调度器投递到 Agent Service | claim lease、持久退避、下游双幂等 | 单次 HTTP、熔断/半开、逐条领取、DELIVERY 日志 |
| 配置与横切 | `config/`、`common/`、`db/migration/` | 独立配置绑定、异步线程池、安全链、指标、trace id、统一异常 | 十二组配置、Flyway V1/V2、Hibernate validate | 兼容聚合、冻结旧库校验、真实 H2/MySQL 升级验证 |

### 9.2 Agent Service（Python / FastAPI）

| 入口/领域 | 当前实现模块 | 本轮完成内容 |
| --- | --- | --- |
| `/chat`、`/chat/stream`、`/conversations/{id}` | `architecture/conversation.py`、`chat_service.py`、`chat_events.py`、`conversation_*` | JSON/SSE 共用流水线、受限主题记忆、续租与预算、最终引用与取消 |
| 执行计划与分发 | `architecture/orchestration.py`、`planning.py`、`topic_routing.py`、`call_limits.py` | 计划链、四模式注册表、授权澄清、请求与会话上限 |
| 授权检索 | `retrievers.py`、`chunk_index.py`、`text.py`、`evidence_sources.py`、`evidence_budget.py` | 词项倒排、并行 hybrid、租户 revision、主题过滤与相邻块预算 |
| 文档/媒体摄取、向量维护 | `database.py`、`rag.py`、`media_ingestion.py`、`vector_codec.py`、`embedding_maintenance.py` | 二进制与 JSON 兼容、有界后台补齐，请求只计算 query 向量 |
| 六阶段分析/发布/知识治理 | `analysis_*`、`publication_*`、`knowledge_lifecycle_store.py` | 业务规则保持，路由 façade、DDL 与 specialist 配置收口 |
| 图谱 | `graph_store.py`、`graph_algorithms.py`、`graph_rag.py` | 授权数据的纯算法与存储分离 |
| 工单、审批与工具 | `ticket_store.py`、`ticket_domain.py`、`tools.py` | 纯规则/存储分离，审批与审计保持 |
| 指标与日志 | `chat_metrics.py`、`chat_observability_store.py`、`tool_observability_store.py` | JSON/SSE 共用计量，原 trace/反馈/影子路由继续可读 |
| 配置、迁移与启动 | `config.py`、`schema/`、`database.py`、`serve.py`、`main.py` | 单一 Settings、八项编号迁移与 ledger、默认单 worker、显式线程额度；m008 修复 MySQL 长文本 |

### 9.3 React Web

| 功能页 | 当前入口 | 本轮完成内容 |
| --- | --- | --- |
| 登录与 Workspace | `AuthGate.tsx`、`WorkspaceSwitcher.tsx`、`useWorkspaceSession.ts`、`App.tsx` | 沿用 JWT，按身份/Workspace/角色重建 QueryClient 与会话；目录/成员 GET 可取消 |
| 证据问答 | `features/QAView.tsx`、`features/qa/`、`hooks/useConversation.ts`、`chatApi.ts` | 四组件、SSE、追问、停止、新建，手机布局与长 trace 换行 |
| 媒体、分析、图谱、工单 | 对应 `features/`、领域 API 与 feature hooks | HashRouter、TanStack Query、退避轮询/AbortSignal、viewer 写入口禁用 |
| 监控 | `MonitorView.tsx`、`observabilityApi.ts` | 保留上一批新增的路由一致率与不一致配对 |

## 十、历史优化前后对比（2026-09-12，`7195dad` 对比 `9410ef3`）

### 10.1 学习 Nexus 的方式：借什么、改什么、不借什么

| Nexus 的做法 | 本项目的落地形态 | 为什么不照搬 |
| --- | --- | --- |
| 前置编排器五步链（路由、改写、歧义检测、子问题拆分、知识域收缩），Java Bean 链 | 三步链 `classify_intent` → `decide_mode` → `plan_queries`，复用已有 LLM 路由与规则降级，standard 请求可跳过前后两步 | 本项目没有多知识库路由，改写与子问题拆分已在 `plan_queries` 内；先把已有函数变成可跳过的步骤，比新增五个步骤更稳 |
| `ExecutionMode` 枚举 + Spring 注册表 | dataclass 注册表，四种模式，重复注册或未知模式直接报错 | 无 DI 容器，注册表本身 40 行足够 |
| 澄清五条件 + 相对置信度 `top1 / max(10, top1 + top2 + 5)` | 只做了"无内容锚点即澄清"；置信度公式留作 0.6 | 公式的输入是候选文档路由分，本项目当前没有这一层，硬套会造成假澄清 |
| 证据预算 2200 / 5200 字符 | 数字相同；先按分数选，再裁，不重排 | 与本项目的覆盖率门控叠加而不是替换 |
| 模型 8 次 / 工具 6 次，会话累计 40 / 30 | 每请求 8 / 6，ContextVar 绑定，超限降级不报错；会话累计未做 | 尚无会话概念（阶段 2）；降级优于报错，因为规则路径本来就是一等公民 |
| AOP 阶段耗时落表 + 三个观测查询接口 | `TraceStep.duration_ms` 随已有 `trace_json` 落库 | 不加新表，`/chat-logs/{id}` 已能回放 |
| `classpath:prompt/*.st` 模板 | `app/prompts/*.txt` + `string.Template`，`AGENT_PROMPT_DIR` 覆盖 | 保留提示词内的 JSON 示例，`${}` 占位不与 `{}` 冲突 |
| 影子路由对比"用户选的文档 / 系统会选的文档" | 对比"用户传的 `workflow_mode` / 系统会选的模式" | 本项目的人工选择点是工作流模式而不是文档 |
| 精排失败不伪造分数 | 相同：`rerank_status` 三态 + `rerank_skipped` trace | 直接采纳 |
| Neo4j、PGVector、ES、Kafka、WebFlux | 不引入 | 见第六节；单机 SQLite + 进程内缓存尚未成为瓶颈，10.3 的数字是证据 |
| "Python 出能力，Java 做决策" | 不改：Agent Service 拥有决策与治理 | 两服务边界已清晰且有 ADR，翻转边界收益为零 |

### 10.2 代码结构对比

以下数字用 `git grep` 对两个提交统计，可复现。

| 指标 | 优化前 `7195dad` | 优化后 `9410ef3` | 说明 |
| --- | --- | --- | --- |
| Agent 应用代码行数 | 13,172 | 14,521 | 新增约 1,350 行，其中测试外的新模块 6 个 |
| Agent 测试文件 / 用例 | 23 / 158 | 25 / 199 | 新增 `test_chunk_index.py`、`test_request_budgets.py` |
| `orchestration.py` | 101 行，按 `workflow_mode` 二选一 | 266 行，链 + 注册表 + 预算 | 决策逻辑从 `agentic_rag.py` 搬到这一层 |
| `planning.py` | 不存在 | 355 行 | 执行计划、链、计时器、澄清门、工具判定、影子路由 |
| `retrievers.py` | 478 行（含 chunk 加载与缓存） | 383 行 | 加载与缓存拆到 `chunk_index.py`（198 行），分词拆到 `text.py`（115 行） |
| `agentic_rag.py` | 781 行 | 834 行 | 路由 / 规划改为链步骤，工具触发词搬走，证据预算接入 |
| 提示词字面量（`llm.py` + `llm_router.py`） | 4 段内联 | 0 | 10 个模板文件 |
| `os.getenv` 调用点 / 文件 | 46 / 12 | 47 / 13 | 未收口，阶段 3.1；新增的是 `AGENT_PROMPT_DIR` |
| `init_db()` 调用点 | 18 | 18 | 未收口，阶段 3.2 |
| `create table` 出现的文件数 | 7 | 7 | 未收口，阶段 3.2 |
| 路由直接导入实现模块（`grep` 近似，不含 auth / models） | 11 处 | 11 处 | 未收口，阶段 3.3 |
| HTTP 契约 | — | 只增不删 | `AgentSummary` +2 字段、`TraceStep` +1、`ChatMetricsSummary` +5、`chat_metrics` +3 列 |

结论：三批优化只重排了 `/chat` 这一条链路及其检索层，配置、DDL、façade 收口三项"体检指标"一个都没动，它们属于阶段 3。

### 10.3 检索热路径对比（合成语料基准）

`quality/agent-evals/bench_retrieval.py`：单租户合成语料，每个文档 1 个 chunk，20 条查询各跑 5 轮共 100 个样本，哈希 embedding、无 fastembed、`LLM_ROUTER_ENABLED=0`，与 CI 条件相同。"优化前"用 `git archive 7195dad` 导出的源码树在同一台机器同一进程条件下运行。日志：`runtime/opt-bench-retrieval.log`。

| 语料规模 | 指标 | 优化前 | 优化后 | 变化 |
| --- | --- | --- | --- | --- |
| 2,000 chunk | keyword p50 / p95 | 64.2 / 90.3 ms | 5.9 / 9.4 ms | 约 1/10 |
| 2,000 chunk | hybrid p50 / p95 | 83.8 / 94.2 ms | 26.4 / 49.7 ms | 约 1/3 |
| 5,000 chunk | keyword p50 / p95 | 159.8 / 178.4 ms | 14.5 / 51.4 ms | 约 1/10 |
| 5,000 chunk | hybrid p50 / p95 | 216.2 / 249.0 ms | 102.4 / 119.7 ms | 约 1/2 |
| 2,000 chunk | 写入后首次检索（缓存重建）keyword / hybrid | 124.8 / 156.0 ms | 178.2 / 241.7 ms | **慢约 45%** |
| 5,000 chunk | 写入后首次检索（缓存重建）keyword / hybrid | 321.6 / 388.6 ms | 450.1 / 602.5 ms | **慢约 45%** |
| 5,000 chunk | 摄取总耗时 | 21.4 s | 21.3 s | 不变 |

怎么读这张表：

- 关键词路径从 O(N·L) 变成 O(命中数)，语料翻 2.5 倍时优化前耗时翻 2.5 倍，优化后 p50 只从 5.9 涨到 14.5 ms。这是 1.1 + 1.2 的直接结果。
- hybrid 的收益小于 keyword，因为 embedding 通道仍是全量余弦扫描，并行只能把它和关键词通道重叠起来；embedding 通道本身要靠 1.3 二进制向量才会明显变快。
- 缓存重建变慢是真实代价：重建时要对每个 chunk 预计算词项并构建倒排。1.6 的按租户失效缓解了它（一个租户写入不再重建其他租户），但同租户内每次写入后的首个请求仍付这笔钱。1.5 把 embedding 补齐移出请求路径后会再降一部分。这个代价没有写进 QUALITY 的门禁数字里，因为黄金集语料只有几十个 chunk，测不出来。
- 黄金集的 p95（6 到 9 ms）在三批前后没有可辨识的变化，属于噪声；这也是要另做合成语料基准的原因。

### 10.4 质量门禁对比

| 门禁 | 优化前（2026-09-11 收尾） | 三批之后 | 说明 |
| --- | --- | --- | --- |
| Agent 全量 | 158/158 | 199/199 | 旧用例仅两处断言改为接受 `plan=ANY` |
| V6 hybrid decision / recall@3 / fact | 98% / 97% / 97% | 98% / 97% / 97% | 关键词路径结果顺序被证明与旧实现逐 query 一致，指标不变是设计结果 |
| V6 embedding-only（不设门禁） | 88% / 84% / 81% | 88% / 84% / 81% | 中间一次跑出 88/81/78，两次重跑恢复，原因未定位 |
| PRD | 12/12，十项指标 100% | 同 | 未改动 |
| Knowledge Lifecycle、V5 观测 | 通过 | 通过 | 未改动 |
| Web lint / test / build | 0 error 18 warning / 7/7 / 通过 | 同 | 监控面板改动未引入新告警 |
| 黄金集 42 问 | — | 无一被澄清门或工单直达门误拦 | 新增的门只拦"为什么？"这类无锚点问题 |

一句话总结：**行为一致性有黄金集和暴力对照证明，效率收益有合成基准证明，结构收益有行数与模块划分证明；证据预算、调用上限、影子路由三项目前只有"机制存在且测试覆盖"的证据，还没有真实流量下的收益证据。**

### 10.5 当时尚未兑现的承诺（历史，当前状态见十一节）

- 证据预算在 600 字符切块下永远不触发，要等长媒体转写片段或 1.7 Parent-Child。
- 影子路由的"系统会选什么"是一套未经验证的规则，需要真实请求积累一致率后再决定是否开启自动模式。
- 调用上限 8 / 6 是照抄的默认值，本项目单次请求最多 4 次模型调用，它现在是兜底不是成本控制。
- 阶段 3 的配置、DDL、façade 收口三项体检指标完全没动，阶段 2 的会话记忆与流式输出是用户能直接看到的差异，建议作为下一批。


## 十一、2026-09-13 接手结果与交接

本轮基线为 `40c2093`，接手时 Agent 199 个用例；当前仍在 `main`，本轮改动未提交。原迁移来源保持只读，保留模型选择、两后端/统一前端、JWT scope、证据、审批和审计。

| 项目 | 接手前 | 当前工作树与证据 |
| --- | --- | --- |
| Agent 回归 | 199/199 | 244/244，新增/扩展会话、向量、配置、迁移与 MySQL 兼容回归 |
| 会话/流式 | 无 | window/summary、两种传输、续租、预算与取消；Conversation V1 9/9 |
| 业务环境读取 | 13 个文件 | 仅 config.py；旧 API 兼容，启动类型校验 |
| DDL | 分布在 7 个领域文件 | schema 包统一八项编号迁移与 ledger；SQLite 与真实 MySQL 旧库/双进程启动、长文本保存通过 |
| routes 依赖 | 业务实现直接导入 | architecture 入口；基础类型例外显式列出，静态门禁 |
| Web / localhost | 7 个 Web 用例 / 33 项验收 | 21/21；H2/SQLite 与真实中间件各 42/42；路由、Query、会话与 viewer UI 通过 |
| Media | 135 个用例 | JDK 17.0.18 下 150/150；职责/配置拆分、Flyway V1/V2、阶段日志、熔断通过 |
| 检索/分析质量 | V6 hybrid 98/97/97，PRD 12/12 | V6 hybrid 98/97/97（p95 16.1ms），PRD 12/12 十项 100%；Lifecycle、V5 通过；本机耗时不作提速声明 |
| 数据与恢复 | 轻量环境证据 | MySQL 8.4 迁移 6 项；两库 33 表/518 行备份恢复摘要一致；Agent 断连后 4 事件全部 SENT |

按 `git show 40c2093:<path>` 与当前工作树的相同非空行口径，入口职责收敛如下。原业务代码移到对应服务/配置/controller 中；这些数字衡量阅读入口的规模，性能证据仍看实际评测。

| 入口 | 接手前非空行 | 当前非空行 | 职责去向 |
| --- | --- | --- | --- |
| `VideoTaskService.java` | 415 | 210 | quota/lease/completion 服务 |
| `AppProperties.java` | 490 | 70 | 十二个独立配置绑定组 |
| `apps/web/src/main.tsx` | 488 | 8 | App、Router、feature hooks |
| `features/QAView.tsx` | 463 | 311 | 四个 QA 子组件与会话/controller |

验证命令：Agent `python -m unittest discover -s tests -q`；根目录 ruff、V6/PRD/Lifecycle/Conversation/V5、维护单测；Web lint/test/build；Media `mvn -q test`；`scripts/local_acceptance.py`；`scripts/update_knowledge.py` 与 `--check`。评测使用 hash embedding、`LLM_ROUTER_ENABLED=0`；最新日志与运行范围见 `knowledge/QUALITY.md`。

采用受约束的字面指代补全、同一应用流水线加事件 sink、Agent 自有编号迁移和默认单 worker，是本轮对初始方案的具体化；Media 使用 Flyway，Web 使用 Router/Query，详见 ADR-0016/0017/0018。真实中间件沿用已批准的 MySQL、Redis、RocketMQ 和 MinIO，没有引入新的基础设施类别。未进行二进制向量/新增 worker 的大语料或吞吐基准；第十节的速度变化只属于当时两个提交。

当前授权的架构优化已完成。新增配置与迁移见 `knowledge/OPERATIONS.md`，逐项验收日志和备份位置见 `knowledge/QUALITY.md`。下一次如进入部署阶段，先在目标库副本演练备份/升级，并按正式 Keycloak/RS256、外部 AI、长时间容量、多实例与对象存储灾备补证；本轮未升级或部署既有用户服务。处理任务恢复仅自动关闭旧处理阶段，DELIVERY 的硬崩溃 RUNNING 关联恢复仍是观测边界，不影响 outbox lease 到期后重投。

交接位置：`main@40c2093` 的未提交工作树；新增 ADR-0016/0017/0018 与阶段契约均在本仓库。知识生成/漂移、语义路由和 diff check 已通过。本轮 `codex-stage4-f4819d11` 测试容器/卷及应用/浏览器已清理，保留 `runtime/codex-stage4-*` 日志、MySQL 归档和 `output/playwright/stage4-*.png`。原三容器应用与 `erp-mssql` 保持运行。后续维护先运行 harness brief，核对本节与 `QUALITY.md` 最新条目，勿重跑一次性改造脚本或直接覆盖现有运行数据。
