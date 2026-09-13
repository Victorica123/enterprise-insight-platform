# Agent 工程知识

## 六阶段分析

1. 意图识别：识别会议目标、任务类型和期望交付物。
2. 干系人识别：识别决策者、使用者、执行者、受影响方及立场。
3. 领域深挖：按业务流程、数据、技术约束、规则和术语等维度提取材料事实。
4. 异常与风险：识别矛盾、缺口、依赖、合规与交付风险。
5. 收敛检查：把事实、推断、假设、待确认项分层，判断是否可生成 PRD。
6. PRD 生成：生成带来源、验收口径、风险和未决问题的可评审草案。

阶段是可观测的业务节点，不等同于必须绑定某个 Agent 框架。每一阶段接受结构化状态并产生可校验输出。

当前实现位于独立的 `analysis_evidence`、`analysis_pipeline`、`analysis_store`、`publication_service`、`publication_artifacts`、`knowledge_lifecycle_store` 与 `routes/analysis` 模块，没有继续扩张已有的 `agentic_rag.py`。创建会话时，`analysis_evidence` 先在 JWT 限定的 tenant/owner/asset scope 内用 hybrid 检索按 objective 排序，最多冻结 24 个正分 chunk；canonical JSON、content revision 与 SHA-256 随 session 持久化。`analysis_pipeline` 仍是无外部模型的确定性基线，但领域阶段现在通过进程共享、默认 4 worker（`AGENT_SPECIALIST_WORKERS`）的线程池并行执行业务、数据与安全、技术与集成、规则与合规四个 specialist；结果按固定声明顺序合并，单维失败进入人工复核，显式冲突进入 `domain_conflict`。这些 specialist 是有界领域执行器，不声称是独立 LLM Agent。

事实不足时返回结构化问题和恢复令牌；补充后保持同一 session，读取创建时的冻结证据，保留阶段 1–4，只重新执行收敛和 PRD 阶段。目标、证据排序、早期结论和恢复输入因此可以复现，不受等待期间新摄取材料影响。

## 对话执行计划

- 每次对话先由 `PreparationChain`（`app/architecture/planning.py`）生成一份冻结的 `ExecutionPlan`：`classify_intent`（LLM 路由，规则降级）→ `decide_mode` → `plan_queries`（LLM 规划，规则降级）。步骤可单独跳过：`workflow_mode=standard` 跳过分类与规划，只做模式决策，单轮检索路径不多调模型。
- 模式决策顺序为 clarify > （显式 standard → retrieval）> tool_only > agentic。`workflow_mode` 保留为兼容输入，服务端以 `plan.mode` 为准；`AgentSummary.execution_mode` 与 trace 中的 `execution_plan` 步骤记录最终决定与生成它的步骤列表，可回放。
- 澄清门保留无内容锚点规则，并在已授权客户/项目候选上使用相对置信度 `top1 / max(10, top1 + top2 + 5)`（阈值 0.55）。单候选放行，明确主题或主动比较不误拦，无候选仍进入原证据不足路径；不会把“原因/风险”等兼容意图当作互斥知识域。当前标识提取为受限字面规则，见 `topic_routing.py`。
- `ExecutorRegistry` 按模式注册唯一执行器：`ClarificationExecutor`、`ToolOnlyExecutor`、`RetrievalExecutor`（`rag.answer_question`）、`AgenticExecutor`（`agentic_rag`）。agentic 执行器复用计划里的分类结果与 query，不重复调用路由模型；未注册的模式直接报错而不是静默降级。
- 每个 `TraceStep` 带 `duration_ms`：链内每步、检索、图谱、工具、生成、引用审核各自计时，随 `chat_logs.trace_json` 落库；旧日志该字段为 null。
- 每请求调用预算（`app/call_limits.py`）：`ConversationOrchestrator.run` 用 ContextVar 绑定一个 `LimitCounter`，模型调用上限 8 次、工具调用上限 6 次（`AGENT_MAX_MODEL_CALLS` / `AGENT_MAX_TOOL_CALLS`）。只有真正出网的 `create_chat_completion` 消耗模型预算；超限抛 `CallLimitExceeded`，路由 / 规划 / 工具选择退回规则，答案生成退回模板并写 `answer=call_limited`。工具超限不执行、不进审批，记一条 `limited` 审计后返回失败结果。请求结束时若有任何预算申请，追加一条 `call_limits` trace（超限为 degraded）。未绑定请求的调用（后台任务、工单路由直调、单元测试）不受限。
- 证据字符预算（`app/evidence_budget.py`）：来源按最终检索名次选出（`MAX_SOURCES=4`），再扩展授权的同文档同章节相邻块，最后按单来源 2200、总量 5200 字符裁剪（`EVIDENCE_SOURCE_CHAR_BUDGET` / `EVIDENCE_TOTAL_CHAR_BUDGET`）。句末优先、省略号标记，剩余不足 120 字符时丢弃后续来源。主题过滤在 Top-K 与块扩展两处生效，避免不同客户的邻块重新混入；视频不合并。证据门控、模型和引用审核使用同一份预算后证据，trace 为 `evidence_budget` 或 `evidence_budget_<round>`。
- 影子路由：`decide_mode` 在写入实际模式的同时用规则版 `shadow_decision` 记录"不带 `workflow_mode` 时系统自己会选什么"（clarify > tool_only > 复杂 / 需要工具 / 风险因果意图 → agentic > retrieval；链上已有分类结果时复用，不多调模型）。`ExecutionPlan` 新增 `shadow_mode` / `shadow_reason` / `mode_agreement`；`chat_metrics` 新增 `execution_mode`、`shadow_mode`、`mode_agreement`（-1 为未评估）；`/metrics/summary` 新增 `execution_mode_usage`、`shadow_mode_usage`、`mode_agreement_samples`、`mode_agreement_rate`、`mode_disagreements`，监控面板显示"路由一致率"与不一致配对。它只记录不改变决策，用于在切换自动模式前用真实流量评估规则。

## 会话与流式传输

`chat_service.py` 是 JSON/SSE 的共用应用流水线。`conversation_store.py` 保存会话、已完成轮次、摘要、revision 与预算；`conversation_lease.py` 默认每 40 秒续租 120 秒租约，过期或被替换不得复活。领取时预留当轮额度，正常完成或可处理取消后退还未用部分；会话累计模型 40 / 工具 30，摘要也计入同一模型预算。崩溃预留保守计费，业务写操作仍走原审批。

`conversation_memory.py` 的 none/window/summary 只读取最近四轮用户问题（2200 字符）和可选摘要（1400 字符，每次最多六个旧轮次）。规则补全受限客户/项目标识，模型仅可压缩已有主题；虚构标识触发回退。旧回答不送入本轮证据，每轮都重新取得授权活跃来源。显式换题覆盖旧主题，多主题比较后的指代保持歧义。

`chat_events.py` 用 64 项队列、15 秒心跳和取消信号连接同步执行器；异步答案 provider 的总时限为 timeout × (retries + 1)。本地模板计算完才分片，API 答案可先发待审核 delta；`done` 才携带引用审核结果。前端停止会关闭 fetch，上游流随之取消；同步阻塞规划受调用超时约束。会话已完成但客户端未收到 done 的情况不自动重放。

Conversation V1 九场景覆盖连续指代、摘要、显式换题、两种歧义、删除/替换后的新证据、owner 隔离和同章节跨客户合并。它是合成规则回归，真实模型质量需要单独评估。决策与验证边界见 ADR-0016。

追问由 `follow_up.py` 根据本轮预算后证据生成最多三个规则建议：携带问题里的客户/项目主题，跳过当前问题与最近四轮同一明确主题集合中已问的意图，拒答时不推荐。去重只使用授权会话中的用户问题及其字面主题补全，不读取历史答案或模型摘要；每个历史问题最多 550 字符。不同客户/项目、比较主题集合不会互相屏蔽，`memory_mode=none` 不使用历史去重。它不额外调用模型，JSON/SSE 使用相同结果；不声称实现开放式 LLM 推荐或全会话永久去重。

## 证据策略

- 关键结论必须绑定至少一个可访问证据，或明确标记为假设/建议。
- 视频证据引用稳定资产与片段身份、开始/结束时间、说话人和摘录。
- 发布后的 PRD 以规范 JSON 的 SHA-256 固化为不可变版本；派生知识候选和行动项保留原 requirement 与证据引用，不能脱离来源重新生成事实。
- 批准知识采用规范 Markdown 物化，保存 candidate ID、PRD version、analysis session、内容 SHA-256 与原始证据；后续检索来源明确标记为 `approved_knowledge`。
- 已批准知识通过独立生命周期申请演进：替代创建新的不可变知识版本并双向链接前驱/后继，撤回软失效当前版本；未来检索和图谱只读取活跃 document，历史聊天回放保留原引用并显示当前失效状态。
- 检索结果在进入模型前完成权限过滤；模型不能扩张检索范围。
- 最终答案校验引用存在、归属正确、时间范围有效，并拒绝伪造引用。

## LLM 通道与结构化输出

- `app/llm_client.py` 统一复用 OpenAI-compatible client，并允许调用方传入 `response_format`；超时、重试和最大输出 token 仍由统一配置控制。每次调用带 `purpose` 标签进入每请求模型调用预算。
- 提示词外置在 `app/prompts/*.txt`（`answer_system` / `answer_user` / `answer_source_item` / `answer_context_section` / `router_*` / `planner_*` / `tool_selector_*`），用 `string.Template` 的 `${name}` 占位以保留提示词内的 JSON 示例；`llm.py` 与 `llm_router.py` 只做变量填充，进程内缓存，`AGENT_PROMPT_DIR` 可按部署覆盖同名模板而不重建镜像。缺占位符在渲染时报错，不会发送半填充的提示词；`PROMPT_CATALOG` 声明每个模板必须有的占位符，由测试校验。
- `app/llm_router.py` 的 Router、Planner 和工具选择通道使用固定版本的 JSON envelope。`LLM_RESPONSE_FORMAT=auto` 时，OpenAI 使用 `json_schema + strict=true`；DeepSeek 兼容通道使用 `json_object`，随后仍执行类型、枚举、白名单和参数对象校验。
- 为满足严格 JSON Schema 对根节点和闭合 object 的约束，Planner 返回 `{ "queries": [...] }`，工具选择返回 `{ "calls": [...] }`；工具参数以 JSON object string 传输，再由服务端解析并交给既有工具 schema/权限校验。未注册工具、非法参数、解析失败或 provider 不支持 response format 都只能进入规则降级，不能直接执行副作用。
- 每次 LLM 路由调用读取 provider 返回的 prompt/completion token；现有聊天观测将其与答案调用合并并按配置价格估算成本。token 统计不代表模型质量，必须与独立 holdout、引用正确率、拒答质量、人工接受率、延迟和成本评测一起解释。
- 六阶段 `analysis_pipeline.py` 仍是确定性 specialist baseline；本节的结构化 LLM 通道不应被包装成已完成的多 LLM Agent Runtime，也不改变证据快照、人工审批和授权前置不变量。

## 检索与缓存实现

- hash embedding 是 64 维字符 n-gram 的离线保底；本地 BGE 可用时批量生成 512 维 `embedding_v2`，失败时整体回退，不留下混合维度结果。
- 两套向量新增 float32 二进制列，旧 JSON 双写并可回退读取；旧数据由后台每批默认 64 条补齐，推理不持有写事务，提交前复核内容与文档活跃状态。请求缺少完整语义向量时走 `hash_backfill_pending`，不在检索期间补算文档向量。未据此宣称新性能倍数。
- hybrid 共用一次授权快照，先过滤各通道，再融合。keyword 相对阈值默认 0.35；semantic/hash 的 0–100 分数下限分别为 45/10。真实语义路径用 RRF（K=60），平局优先 keyword 覆盖分；哈希降级明确为 `keyword_then_hash`，保留合格关键词名次，再补 hash 独有候选，不把词面碰撞当作独立语义投票。
- `RetrievalHit.selection_rank` 与 `score` 分开：standard/agentic Top-K、预算顺序及分析快照保留最终名次，标题先验位于融合之前；证据门控继续使用接受信号的固定 0.5/0.5 相关性分。失败通道不重归一化，多轮去重保留最佳名次、最高相关性与 query 并集。
- `retrieval_execution.py` 为 keyword/embedding/rerank 提供进程共享的独立有界池，每通道默认 4 个在途任务；通道 2 秒、精排 3 秒截止，异常/超时/饱和均可见。ContextVar 与取消/租约 guard 贯穿 worker，迟到结果不能回写；无法强杀的原生推理继续占槽，不额外扩建线程池。见 ADR-0019。
- 可选 cross-encoder 只精排 Top-12，默认关闭；开启前须验证真实模型收益。等长且全为有限数值的结果才能标记 applied；异常、畸形结果、超时、满员均保留精排前排序并写 `rerank_skipped`。每通道 trace 记录原始/接受/最终保留锚点数、阈值、耗时和实际 embedding/fusion 策略；有库但无合格证据与通道全失败分别处理，失败阶段不会被指标误记为已回答。
- chunk 快照 LRU 的 key 包含数据库路径、持久化 content revision 和 tenant/owner/asset scope；revision 按租户维护（`system_meta` 的 `content_revision:<tenant>`），一个租户的写入只让该租户与未指定租户的快照失效，全局重建仍让全部租户失效。快照构建时为每个 chunk 预计算词项集并建立词项倒排，关键词检索只对共享至少一个词项的 chunk 打分；hybrid 两路共用一次快照并并行执行。多进程读不会长期复用旧授权范围或旧内容。
- BGE 向量 LRU 以 model identity + 文本 SHA-256 为 key，最大 512 项；同 batch 去重，缓存只保存向量，不保存原文。该缓存是 embedding 计算复用，不等同于 LLM attention KV cache。
- 两个业务缓存都通过已鉴权的 `/embeddings/status` 暴露进程级 entries、capacity、hits、misses、requests 与 hit rate；统一 Web 监控页展示这些指标。计数不按租户展开、不暴露 key，公开 `/system/status` 不返回缓存流量。
- 工程维护文档另有独立的确定性语义索引，不能被业务检索 API 查询。实现和缓存矩阵见 `TECHNICAL_IMPLEMENTATION.md` 与 ADR-0007。

## 等待与恢复

分析会话持久化 session、阶段结果、结构化问题、答案、恢复令牌、PRD，以及证据 revision/hash 和检查点版本。遇到真实信息缺口时进入 `WAITING_CONFIRMATION`；用户补充后恢复同一业务会话。当前这是阶段级业务检查点，不是 Python 执行栈或框架节点 continuation：进程崩溃时不能从某次模型调用中间继续，当前也没有 AppServer/WebSocket 传输层或企业 IM 专家渠道。

`resume_token` 先在 API 做常量时间比较，最终以 `session_id + tenant_id + owner_id + WAITING_CONFIRMATION + resume_token` 条件执行数据库 compare-and-set；一次成功会提升 `checkpoint_version` 并使旧 token 失效。并发回归测试用两个请求竞争同一 token，结果严格为一个 200、一个 409。若仍有缺口，新 token 只在成功 CAS 中轮换。

当前状态机已实现 `WAITING_CONFIRMATION → DRAFT_READY → PUBLISH_PENDING → PUBLISHED`。发布逻辑位于 `publication_service.py`，交付物投影位于 `publication_artifacts.py`，知识物化与生命周期事务位于 `knowledge_lifecycle_store.py`；schema 已收口到 `app/schema/` 编号迁移。个人空间要求 OWNER 二次明确确认，团队空间要求不同成员四眼审批；状态 CAS、审计、不可变版本和初始交付物同事务提交。

## 受控工具

- 工具参数使用 schema 验证，调用前重复鉴权。
- 读工具和写工具分级；有业务副作用的写工具进入审批。
- 重试只用于幂等调用；每次调用保留 trace、输入摘要、批准者和结果。
- PRD 行动项转工单复用 `create_ticket` 受控工具；生成 pending action 不等于工单已创建，只有审批执行后才产生工单。终态会回写为 `TICKET_CREATED/REJECTED/FAILED`，成功时记录真实 `ticket_id`，重复进入请求保持幂等。

## 自进化闭环

- 坏案例：失败答案进入回归数据，记录期望、实际、证据和失败分类。
- 根因：区分摄取、检索、权限、提示、模型、验证和工具错误。
- 改进：优先修复确定性系统问题，再调整提示或模型路由。
- 知识：发布 PRD 生成保留证据的候选；候选经过独立人工决定后才以托管文档进入未来 RAG。候选状态、文档/chunk 与图索引同事务提交。批准后的替代/撤回再次经过人工门禁，并把版本、软失效、缓存 revision 和图谱替换放在同一事务；不把 PRD 审批等同于知识审批，也不让 Agent 自动改写规则。
- 门禁：任何影响 Agent 行为的变更必须有对应评测案例，不能仅凭演示判断提升。

## PRD 专项评测

`quality/agent-evals/evaluate_prd.py` 使用 12 个冻结手工场景，不调用外部 LLM，评价 decision、问题召回与精确率、objective Top-1、冲突升级、证据完整性、受支持结论、验收可测试性、检查点稳定性和 specialist 顺序。当前本地基线各质量项为 100%，P95 约 22 ms。它是代码回归门禁，不代表真实访谈分布、开放域语义质量或生产延迟；后续需要匿名真实坏案例、holdout 与独立人工评审。

`quality/agent-evals/evaluate_knowledge_lifecycle.py` 使用 personal 替代、personal 撤回和 team 替代三类冻结场景，验证未来检索、版本链、历史状态、tenant 隔离、四眼、重复决定冲突、图谱失效与物理保留。它是确定性治理回归门禁，不代表生产数据量下的图谱重建成本。
