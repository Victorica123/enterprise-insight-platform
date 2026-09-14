# 技术实现详解

本文解释 Enterprise Insight Platform 如何从视频与文档形成可验证洞察，并说明代码框架、关键数据流、Agent/RAG、缓存、权限、可靠性和本地验收。它描述当前已实现事实，不把可选生产组件写成已上线能力。

## 1. 总体框架

系统由三层组成：统一交互层、两类业务后端和独立的工程知识维护平面。Agent 使用 FastAPI + Pydantic + OpenAI-compatible SDK，自研有限业务编排，没有采用 LangChain/LangGraph。选型取舍和改用成熟运行时的条件统一见 [框架答辩](../docs/INTERVIEW_GUIDE.md#framework-choice)；不以无基准的性能或可靠性优势解释自研。

```text
Browser / React 19 + TypeScript + Vite
  ├─ /media -> Spring Boot 3.3 / Java 17 Media Service
  │    ├─ Account / Workspace / JWT / RBAC
  │    ├─ Upload / storage / playback
  │    ├─ Media task / transcript / retry
  │    └─ transactional outbox: transcript.ready.v1
  └─ /agent -> FastAPI / Pydantic Agent Service
       ├─ evidence ingestion / chunk / embedding
       ├─ keyword + vector + hybrid retrieval
       ├─ six-stage analysis / checkpoint / resume
       ├─ PRD / approval / immutable deliverables
       └─ governed knowledge materialization and controlled action tools

Engineering knowledge plane (not customer runtime data)
  Codex Skill -> semantic Top-K router -> generated knowledge index -> source documents
```

选择两个后端而不是强行合成一个服务，是因为媒体处理和 Agent 分析拥有不同的状态机、吞吐特征和失败恢复方式。两个服务共享身份与契约，不共享数据库；React 只在展示层聚合状态。

## 2. 目录和模块职责

| 路径 | 技术与职责 |
| --- | --- |
| `services/media-service` | Spring Boot、Spring Security、JPA、H2/MySQL；拥有账号、Workspace、上传、播放、媒体任务、转写和 outbox。 |
| `services/agent-service` | FastAPI、Pydantic、SQLite/MySQL 兼容持久化；拥有证据、检索、分析、PRD、审批、知识、图谱、工单和评测。生产试点强制 MySQL，SQLite 只用于开发/回归。 |
| `apps/web` | React 19、TypeScript、Vite；统一登录、Workspace 管理、媒体、分析、图谱、工单与监控工作台。 |
| `contracts` | 跨服务 JSON Schema 与事件/HTTP 数据结构；用于先契约、后实现。 |
| `knowledge` | 人工维护的产品、架构、安全、Agent、运维、质量事实及 ADR。 |
| `scripts` | localhost 全链路验收、备份恢复、知识快照和语义索引。 |
| `skills/enterprise-insight-maintainer` | 项目专用维护 Skill、语义检索入口和渐进式参考资料。 |

第一次阅读代码应先看 `docs/START_HERE.md`。`database.py` 负责 document/chunk、摄取回执、embedding 与 revision；DDL 统一在 `app/schema/`，配置统一在 `config.py`。`conversation_store.py` 持有会话与预算，`chat_observability_store.py` 持有指标、日志、反馈与历史来源状态。图谱按抽取、纯算法、存储分为 `graph_extraction.py`、`graph_algorithms.py`、`graph_store.py`；工单按纯规则与存储分为 `ticket_domain.py`、`ticket_store.py`，工具审计独立放在 `tool_observability_store.py`。

为对齐智能体技术架构全景，应用层新增 `app.architecture` façade：`conversation` 负责 JSON/SSE 应用流水线，`orchestration` 负责执行计划与四模式分发，`retrieval` 统一授权检索与证据校验，`execution` 暴露六阶段分析、Agentic RAG 和受控工具，`knowledge` 聚合文档/媒体摄取，`governance` 聚合发布、生命周期、行动项和检查点，`observability` 聚合问答与工具观测。路由业务依赖只经这些入口（身份、配置与 DTO 为基础例外），旧平铺模块仍是向后兼容的实现适配器。该重构只改变内部依赖方向，不改变外部 HTTP、事件、JWT 或审批语义。

## 3. 核心业务纵向链路

### 3.1 视频到证据

1. 生产试点配置支持 OIDC Authorization Code + PKCE、Keycloak token 映射及 Media RS256 active-Workspace JWT；当前本机部署使用本地账号与 HS256，不能把支持路径当作正式身份集成已验收，具体环境见 OPERATIONS。
2. Spring Security 将受信 claims 重建为 `WorkspacePrincipal`，后续代码不读取客户端自报角色头。
3. 上传服务把文件写入租户范围内的媒体目录，同时创建持久化媒体任务。分片、直传和普通上传都绑定 tenant、owner 与上传会话。
4. 媒体任务完成后生成结构化转写片段，每段带稳定 segment ID、开始/结束毫秒、说话人和文本。
5. Media Service 在业务事务内写入 `transcript.ready.v1` outbox；调度器异步投递，瞬时错误指数退避，契约冲突进入 DEAD。
6. Agent Service 使用 `event_id` 和 `tenant_id + asset_id + transcript_version` 两级幂等摄取；同版本不同内容返回 409，不覆盖旧事实。
7. 文本分块后同时写入确定性 hash embedding，并在本地 BGE 可用时写入 `embedding_v2`；时间戳和媒体身份一直随 chunk 保留。

### 3.2 证据问答

1. Agent Service 从 JWT 得到 `tenant_id`、`owner_id` 和 `workspace_type`。personal 查询绑定 tenant + owner，team 查询绑定 tenant；过滤发生在检索前。用户选定 `asset_ids` 时只收窄视频来源，当前 Workspace 内已授权的上传文档和 `ACTIVE` 受治理知识仍参与检索，避免视频筛选意外切断知识沉淀闭环。
2. Router 判断问题意图与复杂度，Planner 生成原问题、改写和补充 query。两者与 B2 工具选择均通过 `response_format` 请求结构化 JSON：OpenAI 使用严格 JSON Schema，DeepSeek 使用 JSON Object；服务端再做枚举、类型、工具白名单和参数校验，失败统一降级到规则路径。
3. Retriever 可选择 keyword、embedding 或 hybrid。hybrid 的独立有界通道先过滤弱候选；真实语义路径用 RRF（K=60），hash 降级保留关键词优先并标记 `keyword_then_hash`。可选 cross-encoder 只重排 Top-12；最终名次独立于相关性分，回答层不再覆盖融合/精排名次，证据门控仍使用实际分数。通道异常、超时、饱和与最终保留数均进 trace，见 ADR-0019。
4. Evidence Agent 判断证据是否足够；复杂问题最多进行受限轮次补查，不无限循环。
5. 本地模板或 LLM 生成后，Reviewer 检查标准来源标记与部分数字/日期锚点，缺引用时补列表；可疑陈述仅告警，尚无严格语义阻断。来源授权与视频定位由前序数据/检索及播放链路约束，不能把它们当成答案逐句支持性验证。
6. 前端点击视频引用时向 Media Service 请求短时播放 token；Agent Service 不保存对象存储凭证。

`LLM_RESPONSE_FORMAT=auto` 是兼容策略，不是模型质量保证：`json_schema` 请求被 provider 拒绝、网络失败、拒答或 JSON 解析失败时，Router/Planner/Tool Agent 记录降级并继续使用确定性规则。工具选择的严格 envelope 使用 `{ "calls": [...] }`，每项将不同工具的参数编码为 `arguments_json` 字符串，解析后仍必须经过工具定义和执行前鉴权。当前 `analysis_pipeline.py` 的四个 specialist 仍是规则基线；结构化 LLM 通道不等同于完整多 LLM Agent Runtime。

问答的 JSON/SSE 传输共同进入 `chat_service.py`：领取会话租约与预算 → 有界主题提示 → ExecutionPlan → 授权检索 → 相邻块扩展与证据预算 → 生成 → 引用审核 → 持久化最终轮次与指标。SSE 使用 64 项队列、15 秒心跳和 AsyncOpenAI 答案流；本地回答完成后分片。Web 只有收到 `done` 才保存最终回答，停止/切换通过 AbortController 与 generation 防止迟到回写。

追问提示只根据本轮授权证据生成，最多三条、排除已问主题，拒答不生成；未增加模型调用。来源排序、通道状态和追问同时覆盖 JSON、SSE 和会话回放。模型级语义引用修复、任意改写和 Pro 五通道检索未纳入当前实现，完整对照见 `docs/NEXUS_REFERENCE_AUDIT.md`。

记忆保留最近四轮问题（2200 字符）和可选摘要（1400 字符，每次最多推进六轮），只补全受限客户/项目标识；旧回答不进入新证据。会话累计模型 40 / 工具 30，数据库预留与退还，默认 120 秒租约每 40 秒续租，旧执行者 CAS 失败不能覆盖新轮次。个人与团队会话沿用 JWT scope，详见 ADR-0016。

### 3.3 六阶段分析和发布治理

分析流程按意图、干系人、领域、风险、收敛、PRD 六个可观测阶段输出结构化 Pydantic 结果，而不是依赖不可检查的长对话。创建会话时，`analysis_evidence.py` 先把 objective 送入 hybrid Retriever；tenant/owner/asset 过滤发生在排序前，最多保留 24 个正分 chunk。系统在检索前后读取持久化 content revision，只有稳定读才把排名、分数、query 命中和必要 chunk 事实固化为 canonical JSON，并记录 SHA-256。embedding 向量不复制进会话快照。

`analysis_pipeline.py` 仍不调用生成模型，但领域阶段通过进程共享、默认 4 worker（`AGENT_SPECIALIST_WORKERS`）的线程池并行执行四个固定 specialist：业务、数据与安全、技术与集成、规则与合规。LLM 结构化输出目前只覆盖问答侧的 Router、Planner 和 Tool Agent，不改变六阶段分析的确定性 baseline。每个 specialist 最多投影 4 个证据片段；主线程按声明顺序而非完成顺序合并。单个任务异常被隔离为 `specialist_review`，显式“冲突/矛盾/口径不一致”被合并为风险并产生 `domain_conflict`，没有无限 loop 或无界 fan-out。这里的 specialist 是本地确定性领域执行器，不冒充独立 LLM Agent。

证据不足时，会话进入 `WAITING_CONFIRMATION` 并保存 session、阶段结果、问题、答案、恢复 token、证据 revision/hash 和 `checkpoint_version`。用户补充后从内部快照恢复，原样保留阶段 1–4，只重算收敛和 PRD。保存使用 `WHERE session_id + tenant_id + owner_id + status=WAITING_CONFIRMATION + resume_token` 的 compare-and-set；一次成功后检查点版本递增，竞争请求得到 409。它是可重放的业务阶段 checkpoint，不是执行栈级 continuation，也没有 AppServer/WebSocket。PRD 从 `DRAFT_READY` 进入 `PUBLISH_PENDING` 后：

- personal Workspace 由 OWNER 使用一次性 token 做第二次明确确认；
- team Workspace 必须由不同的写成员批准，提交者不能自批；
- compare-and-set 状态、审计、canonical JSON SHA-256 版本、知识候选和行动草稿在同一 SQLite 事务提交；
- 知识发布和外部工单仍有各自独立审批，PRD 通过不等于副作用自动执行。

领域任务的异常隔离不含永久挂起：当前 `as_completed` 没有截止时间，共享 ThreadPoolExecutor 队列也未做容量准入。这里限制了输入和线程数，尚无独立 specialist worker；详见 [故障边界](../docs/INTERVIEW_GUIDE.md#fault-isolation)。

### 3.4 批准知识物化与再召回

PRD 发布只生成 `PENDING` 知识候选。授权用户点击“批准并沉淀”后，`knowledge_lifecycle_store.py` 在一个数据库事务内完成：

1. compare-and-set 校验候选仍为 `PENDING`；
2. 从 statement、原 requirement evidence、PRD version、analysis session 与 candidate ID 生成规范 Markdown；
3. 计算 SHA-256，写入内部 `source_type=knowledge` 的托管 document 和 chunks；
4. 同步建立图索引，并把 document ID、hash 与发布时间回写候选。

任何一步失败都回滚，因此不会出现“状态已批准但检索不到知识”。通用文档删除拒绝托管知识，防止绕过治理。Retriever 在授权过滤后读取这类 chunk；公开 `Source` 为兼容旧客户端仍取 `source_type=document`，同时用 `origin_type=approved_knowledge` 和 candidate/PRD/hash 字段证明来源。该实现是“人工门禁后的知识演进”，不是模型自动修改 Skill 或提示规则。

批准知识的 Phase 2 演进使用 `knowledge_versions` 与 `knowledge_lifecycle_requests`。替代不会覆盖 v1，而是物化 v2 并把 v1 标记 `SUPERSEDED`；撤回把当前版本标记 `REVOKED`。`knowledge_lifecycle_store.py` 持有版本物化和事务状态机，schema 与兼容升级归属 `app/schema/`，`publication_artifacts.py` 只保留交付物编排边界。生命周期决定在 `BEGIN IMMEDIATE` 中以 request/candidate CAS 推进，同时更新 document 活跃状态、候选当前指针、content revision 和 owner scope 图谱。`list_chunk_rows` 在 SQL join 阶段只读取 `ACTIVE` document，因此失效知识不会进入模型上下文。聊天日志保存最多 10 条、每条正文最多 1000 字符的来源快照；回放保留原引用，并从 document 表刷新当前生命周期。升级前没有来源快照的旧日志保持为空，不虚构历史证据。

### 3.5 Workspace 协作

Media Service 是成员关系和 active Workspace 令牌的唯一权威。OWNER 创建团队，OWNER/ADMIN 生成 15 分钟一次性邀请，服务端只保存邀请码 SHA-256；用户接受后默认成为 MEMBER。角色映射为 VIEWER→viewer、MEMBER→operator、ADMIN/OWNER→admin。

切换 Workspace 时服务端重新查询成员关系并签发新 JWT。团队资源按 tenant 共享，个人资源按 tenant + owner 隔离；`owner_id` 在团队中仍用于创建者归属和审计，而不是缩小团队读取范围。

## 4. Embedding、混合检索和缓存

### 4.1 业务 RAG 向量

业务 Agent 有两套向量表示：

- `embedding`：64 维确定性字符 n-gram feature hashing，无下载、离线可复现，是功能保底。
- `embedding_v2`：可选 `BAAI/bge-small-zh-v1.5` 本地 ONNX 向量；模型不可用时不会阻断摄取和检索。

真实模型惰性加载并支持显式 warm-up。新增的向量缓存以 `(model object identity, SHA-256(text))` 为 key，value 是不可变向量 tuple：同一 batch 的重复文本只推理一次，跨请求重复文本命中最大 512 项的进程内 LRU。key 不保存原始文本，降低缓存扩大敏感信息驻留面的风险。

文档 chunk 快照（`app/chunk_index.py`）另有一个最大 64 项的 LRU，key 包含数据库路径、持久化 revision、tenant、owner 和 asset 范围。revision 按租户存放在 `system_meta` 的 `content_revision:<tenant>`，未写过的租户读全局值：租户内摄取或删除只提升该租户与全局 revision，embedding 重建、保留清理等全局操作提升全部键，因此多进程写入也能让旧快照自然失效，不需要依赖“当前进程记得清缓存”。快照项同时保存每个 chunk 的词项集与词项倒排（`ChunkIndex.postings`），分词器统一在 `app/text.py`，摄取、检索与评测脚本共用一份。

向量新增带版本头的小端 float32 `embedding_blob` / `embedding_v2_blob`；写入仍保留 JSON，读取优先 blob，缺失或损坏时回退 JSON。后台有界补齐旧数据，模型推理在写事务之外，提交复核内容和活跃状态并只提升受影响租户 revision。检索若发现语义向量未齐，整批使用 hash，状态为 `hash_backfill_pending`；完整时只推理 query，不补算文档。

`evidence_sources.py` 在 Top-K 前做受限主题过滤，并把同文档同章节的授权相邻 child 扩展到来源预算上限。扩展也执行主题检查，避免被排除的客户经邻块回流；`chunk_indices` 保留组成位置，视频片段不合并。二进制与后台补齐目前证明了兼容和路径约束，没有本轮的大语料速度提升数据。

### 4.2 维护 Skill 语义索引

维护知识和客户业务数据完全分离。`scripts/knowledge_index.py` 只扫描仓库内批准的知识、ADR、契约、README、当前运维文档和 Skill 参考，不读取 `docs/archive`、SQLite、媒体、上传内容或 runtime 目录。

索引使用 192 维 `hash-ngram-topic-embedding-v1`：英文/代码词、中文 1~3 gram 与领域 topic alias 共同映射到稳定向量。归一化向量进一步量化为 signed int8 并 Base64 存储，把每个 chunk 的向量载荷固定为 192 字节；查询时解码并执行 cosine。它不需要模型下载，适合提交到 Git 和 CI 重建；它的目标是把维护任务路由到正确文档，不替代业务侧 BGE 语义模型。

缓存分四层：

| 层级 | Key | Value | 失效方式 |
| --- | --- | --- | --- |
| 文档向量增量复用 | chunk 内容 SHA-256 + 算法版本 | 192 维维护向量 | 内容、算法或维度变化 |
| 维护查询缓存 | corpus revision + query digest + Top-K | 文件、标题、行号和分数 | 任一受索引文件、分块版本或向量算法变化 |
| 业务 chunk 快照 | DB path + 租户 content revision + scope | 已授权 chunk 对象、词项集与词项倒排 | 该租户数据写入或全局重建提升 revision |
| 业务真实向量 LRU | model identity + text digest | BGE 向量 | 进程重启、显式清理或 LRU 淘汰 |

业务缓存的 `cache_info` 被统一归一化为 entries、max_entries、hits、misses、requests 和 hit_rate，通过已鉴权 `/embeddings/status` 返回，并在 Web 监控页并列展示。指标只聚合当前进程且重启归零，不包含缓存 key 或 tenant/owner 分组；公开 `/system/status` 只保留覆盖率。这样既能验证缓存是否真正产生收益，也不会通过公共健康检查暴露工作负载计数。多实例生产环境应由 Prometheus 按实例采集后聚合，容量调整必须基于代表性流量而非本地冷启动样本。

这类设计与 KV cache 的共同点是“稳定 key 复用昂贵计算”。但 LLM attention KV cache 属于模型推理引擎能力，本项目没有把普通字典缓存包装成模型级 KV cache，也不会虚构 provider 缓存命中率。Skill 通过稳定短前缀 + Top-K 动态上下文提高潜在前缀缓存友好度，最终是否命中仍由模型运行时决定。

## 5. Skill 如何使用向量知识

`enterprise-insight-maintainer` 保留少量高价值不变量作为稳定入口。跨服务、架构、RAG 或陌生任务先运行：

```powershell
python skills/enterprise-insight-maintainer/scripts/query_project_knowledge.py "任务描述" --top-k 5
```

脚本返回原始文件、标题和精确行号；Agent 随后读取这些原文，而不是相信索引 preview。`knowledge/generated/SEMANTIC_INDEX.json` 是可再生路由数据，不是新的事实来源。更新知识库时统一执行：

```powershell
python scripts/update_knowledge.py
python scripts/update_knowledge.py --check
```

生成器会同时维护结构快照和语义索引；漂移检查阻止 Skill 使用过期框架信息。

## 6. 安全、可靠性与一致性技术点

- 身份：共享 issuer/audience/signature 的 JWT；tenant、owner、workspace type 与 role 由服务端签发。
- 越权隐藏：跨 scope 资源统一按不存在处理，避免枚举资源身份。
- 幂等：上传内容、媒体事件、语义 transcript version、发布 CAS 和工具 action 都有稳定 key。
- 事务 outbox：数据库事实和待投递事件同事务，避免业务成功但消息丢失。
- 可恢复业务状态：媒体任务可重试；Agent 会话冻结授权证据并持久化阶段/答案，确认保留前四阶段、CAS 推进检查点；审批副作用独立治理。
- 不可变发布：canonical JSON + SHA-256，发布版本不可覆盖。
- 原子知识沉淀与演进：候选批准、版本替代或撤回都把托管 document/chunk、当前指针、content revision、图索引与 provenance 放在同一事务；历史版本只软失效，不做 CRUD 删除。
- 证据最小化：跨服务事件不携带 JWT、存储密钥或永久播放 URL。
- 轻重模式分离：localhost mock/local 模式用于无外部依赖验收，不能代替 Redis、MQ、对象存储和真实模型 smoke。

## 7. 前端实现

React 应用只保存一个 active Workspace session。HashRouter 管理六个可刷新/回退页面，`main.tsx` 仅挂载应用，页面状态位于 `useQAWorkspace`、`useAnalysisData`、`useMediaWorkspace`、`useKnowledgeWorkspace`、`useTicketsWorkspace`。QA 会话挂在路由上层，同一身份内换页保留，身份/Workspace/角色变化时重建。

TanStack Query 持有服务器数据，key 包含 tenant、user、role、workspaceType 和领域；token 单纯续期不更换 scope key。Workspace 或角色变化会取消并清空旧 QueryClient，迟到结果不能进入新空间；跨标签页 session 更新采用同一规则。23 个 GET transport 的回归验证 Bearer 与 AbortSignal 贯穿，查询去重、有界重试和媒体退避轮询；上传/审批等写操作不自动重放。viewer 界面禁用媒体、文档、分析写入口，查询与播放仍可用，最终鉴权由服务端执行。

前端请求按业务域拆分：`apiClient.ts` 只处理 JWT、错误映射和 JSON transport，`analysisApi.ts`、`mediaApi.ts`、`knowledgeApi.ts`、`graphApi.ts`、`ticketApi.ts`、`observabilityApi.ts` 各自持有领域 DTO 与请求；`api.ts` 作为兼容 barrel 保留旧导入入口。新增接口不再继续堆入单一总文件。

Workspace 管理弹窗通过 React Portal 挂载到 `document.body`。这是因为 sticky header 的 `backdrop-filter` 会创建新的 containing block，使嵌套的 `position: fixed` 相对 header 而非 viewport 定位。真实浏览器测试在 1280×720 下捕获并验证了该问题。

问答请求独立在 `chatApi.ts`，`hooks/useConversation.ts` 管理连续追问、窗口/摘要、停止和新建。`QAView` 拆成 `QuestionForm`、`AnswerStream`、`SourceList`、`TracePanel`；QA 响应式规则随 QA 样式加载，长执行计划可以换行。SSE 解析测试覆盖 UTF-8 跨包、心跳、事件归属、错误和缺少 done；这些是传输回归，不等同真实供应商验收。

## 8. 验证体系

- Media Service：JUnit/Spring 集成测试覆盖认证、上传、任务、播放、outbox、租户、Flyway、真实阶段日志与熔断。quota/lease/completion 分担任务职责，十二组配置独立绑定，`AppProperties` 保留兼容入口。
- Agent Service：unittest 覆盖摄取、检索、向量回退、分析、发布、工具、隔离与观测。
- Agent 评测：V6 黄金集验证 keyword、embedding、hybrid 的决策、Top-3 来源命中（字段 `recall3`，实为 Hit@3）、任一预期事实子串命中和延迟；后两者不等于严格召回率与逐陈述事实正确率。PRD V1 黄金集验证目标排序、授权隔离、缺口/冲突、引用支持、验收可测试性、检查点和 specialist 顺序；Knowledge Lifecycle V1 验证替代/撤回后的检索、版本链、历史引用、四眼与事务失效。
- Web：TypeScript project build + Vite production build，并补真实浏览器业务操作。
- 平台：`scripts/local_acceptance.py` 使用随机 localhost 端口、H2、SQLite、本地文件和 mock AI 跑 42 项双用户完整纵向链路；同一链路已在 MySQL/Redis/RocketMQ/MinIO、HS256、mock/local AI 隔离环境通过。新旧库、Agent 断连、分片续传、Range、两库备份恢复和有限 k6 分别留证，见 `QUALITY.md`。
- 知识：生成器漂移检查、维护索引单元测试和 Skill quick validation。

## 9. 面试或简历可重点说明的技术价值

1. 不是把两个页面拼在一起，而是用统一身份、tenant/owner、版本化契约和一条业务纵向链路完成系统整合。
2. RAG 不只“有向量库”：检索前授权、混合召回、RRF、可选 rerank、证据门控、引用验证和时间戳回放形成可信链。
3. Agent 不等于一次大 Prompt：Agentic RAG 负责受限检索编排；六阶段用 objective-aware 冻结证据、四类有界确定性 specialist 和阶段 checkpoint 构成可测试基线。等待恢复 CAS、发布审批、不可变版本、批准知识物化和受控工具把分析与副作用分开。
4. 可靠性不是只靠重试：transactional outbox、双重幂等、冲突保留旧事实、指数退避、冻结证据与一次性 resume CAS 共同保证可恢复性；模型调用中断后的节点级执行恢复仍是后续能力。
5. 缓存不是盲目存结果：所有缓存 key 都带模型/内容/数据 revision 或授权 scope，并明确缓存层和失效边界。
6. 工程知识也可执行：Skill、语义索引、ADR、生成快照和 CI 漂移检查让后续 Agent 不必每次重新理解整个仓库。

## 10. 后续生产优化顺序

1. 已按 ADR-0014 固定生产试点的 Keycloak OIDC、RS256/JWKS、30/180/365 天保留期和模型出境 tenant allowlist；若要近实时撤权需另加集中撤销机制。
2. 在已通过的本机 MySQL/Redis/RocketMQ/MinIO 基础上，补目标部署的 Keycloak/RS256、外部 AI、长时间压力、多实例、对象存储灾备与告警，再评估生产可靠性目标。
3. 当业务 chunk 数量超过单机扫描预算时，再引入支持 metadata pre-filter 的向量数据库；迁移前保留当前 SQLite 基线做行为对照。
4. 将现有进程级 embedding LRU/检索快照指标接入 Prometheus，补充 eviction 与冷启动耗时，并依据真实流量调整容量和实例级告警。
5. 模型供应商支持 prompt caching 时，固定 system/tool schema 前缀，动态证据后置，并以 provider 返回的 cached-token 指标验证收益。
