# 工程化落地优化路线

> 2026-08-03 整理。V1–V5 学习版闭环已完成并全部通过评测门禁。
> 本文回答一个问题：把这套系统从"单机学习版"推到"企业可用的生产系统"，按什么顺序改什么、为什么。

## ✅ 已落地（2026-08-07 P0 加固批 + 2026-08-19 A/B 深挖与 P1/P2 工程批）

### P1/P2 工程优化（2026-08-19）

- 文档、chunk、embedding 与增量图谱索引改为同一 SQLite 事务；图谱全量重建在单事务内原子替换，失败保留旧图。
- 删除文档与派生图谱重建同事务完成，避免文档已删但图谱仍残留的中间态。
- `system_meta.content_revision` 驱动进程内 chunk 缓存；同 revision 复用解析后的向量，任意进程写入后自动换 cache key。当前仍是“每个 revision 首次全表装载”，不是 pgvector 的替代品。
- `chat_metrics` 聚合下推 SQLite，避免监控接口把全部历史记录读入 Python；P95 使用有序单点查询。
- LLM SDK client 复用连接池，统一配置 timeout、有限重试和最大输出 token；上传后的解析/embedding/图谱抽取移出 ASGI event loop。
- 修复并发审批：claim 显式返回 ownership，只有获锁者执行 side effect；新增双线程回归。外部系统的崩溃窗口仍需下游幂等键/Outbox，不能宣称任意副作用严格 exactly-once。
- 后端 `main.py` 从约 472 行缩至约 230 行，HTTP 路由拆到 `routes/`；RAG 本地模板、Agent 规划和 citation review 拆成独立模块。
- 前端 `main.tsx` 从约 1800 行缩至约 340 行，QA/工单/图谱/监控拆成 feature；单一 1779 行 CSS 拆为四个样式域。
- 新增 5 个 P1/P2 回归测试，总数 77：事务回滚、图谱重建回滚、revision 缓存、LLM client 策略、并发审批 ownership。

### P0 加固（2026-08-07）

- 图谱/工具上下文真正注入 LLM prompt（旧实现为回答后拼接，模型看不到图谱与工单结果）：`llm.py:build_user_prompt`、`rag.py:build_answer`、`agentic_rag.py:build_answer_with_context`。
- 上传大小限制：`POST /documents` 流式分块读取，超 `MAX_UPLOAD_BYTES`（默认 50MB，可用环境变量覆盖）返回 413。
- SQLite 启用 WAL + `busy_timeout=5000`，且 `database.connect()` 改为 commit/rollback 后真正 close 的上下文管理器（修复连接句柄泄漏）。
- 未携带 `X-User-Role` 的请求默认按 `viewer`（只读）处理，不再默认可写。
- token 成本单价默认值随 `LLM_PROVIDER` 切换（OpenAI 用 gpt-4.1-mini 公开价）。
- 计划文档简历模板改写为如实表述（框架名为"对齐/可迁移"目标而非已用）。

### A/B 深挖（2026-08-19，RAG 检索质量与 Agent 真实性）

- **A1 黄金评测集**：`scripts/golden/`（42 条标注问答 × 4 份多风格语料）+ `scripts/evaluate_v6.py`（decision/recall3/fact 三维裁判，事实子串判定对重切块免疫），基线存档 `baseline_v6.json`；已接入 `context-harness.ps1`。
- **A2 打分纠偏**：停用词过滤；`general` 证据门槛 6→15；锚点门控升级为三级规则（显式实体全匹配 → ≥3 字长词 → ≥2 双字词），修复"配置/BGP/客户C"类误放行；意图覆盖改按同义词组判定；因果句选择按 延迟词+因果词 > 延期原因标签 > 仅延迟词 > 仅因果词 优先级。
- **A3 真实 embedding**：fastembed/BGE-small-zh（512 维 ONNX 本地推理，`requirements-embedding.txt`），chunks 新增 `embedding_v2` 列，检索时真实向量优先、哈希版自动回退；可选 cross-encoder reranker（`RERANKER_MODEL` env 开关，默认关守住延迟预算）；模型启动预热。实测 embedding 模式 recall3 +13.5%、fact +18.9%（vs 哈希基线）。
- **A4 结构感知切块**：标题层级链（"文档 / 章节"）随块入库并参与检索词项、证据锚点与 API prompt；句子级打包与重叠，超长句才硬切；`MAX_SOURCES` 3→4 适配章节级粒度；标题词项加成（+25）用于来源选择。
- **B1/B2 LLM 路由、规划与工具选择**：`llm_router.py` 提供 Router/Planner/工具决策的 LLM 通道（温度 0.1 + JSON 解析 + 真实 token 核算并入成本面板），规则版为自动降级通道；`LLM_ROUTER_ENABLED=0` 全局关闭（离线门禁与测试默认关闭，确定性且零 API 消耗）。
- **B3 声明级溯源**：含数字/日期/百分比的陈述句必须在来源中找到锚点，否则回答附"⚠️ 请人工核对"提示（`find_unsupported_claims`）。

**已知留白（记录在案）**：黄金集 para-04（"质量门槛"→"验收标准/UAT 95%"）在无 LLM 规划时仍拒答——这是留给 B1 LLM 规划的同义改写案例，配置 API Key 后由 `llm_plan_queries` 覆盖；reranker（BAAI/bge-reranker-base，已下载实测，CPU 约 48ms/对）保持默认关闭（`RERANKER_MODEL` 开启即生效），因其对 para-04 类语义改写无增益而延迟成本显著——该类问题归 B1 LLM 规划通道解决。

## 0. 当前基线（已验证）

| 维度 | 学习版现状 | 实测指标（2026-08-03） |
| --- | --- | --- |
| 检索 | SQLite 每 revision 首次全表装载 + 进程缓存，本地/真实 embedding | 小语料正确性基线，不代表生产容量 |
| 图谱 | 规则抽取 + SQLite 两表 + BFS | 召回 100%（演示语料），查询 P95 8.1ms |
| 工具/审批 | 原子 claim ownership + 幂等键 + TTL | 串行和双线程重复审批只允许 claim owner 执行；外部副作用仍需下游幂等 |
| 观测 | chat_metrics + chat_logs + tool_call_logs，token 成本核算 | 观测检查 8/8，chat P95 29.7ms |
| 质量门禁 | evaluate_v2–v6 五道离线门禁 + 77 个回归测试 | 全部通过 |

学习版刻意选择了"零外部依赖、可解释、可离线回归"，这些指标只代表小语料下的正确性基线，不代表生产容量。下面按优先级给出落地改造。

## P0：正确性与安全（上生产前必须做）

### 1. 鉴权与租户隔离
- 现状：`X-User-Role` 请求头自报角色，仅作演示。
- 落地：OIDC/JWT（Keycloak 或企业 SSO）+ FastAPI 依赖注入鉴权；所有业务表加 `tenant_id` 列并在查询层强制过滤；审批操作记录真实用户 ID 而不是角色名。
- 验收：跨租户读写在 API 层 100% 拒绝，审计日志能定位到人。

### 2. SQLite → PostgreSQL + pgvector
- 现状：单文件 SQLite，写并发受限，进程内全表扫描检索。
- 落地：
  - documents/chunks/tickets/pending_actions/tool_call_logs/chat_* 迁 PostgreSQL（现有 DAO 已按函数封装，SQL 方言差异小）；
  - embedding 列换 `vector` 类型，检索改 `ORDER BY embedding <=> query LIMIT k` 走 HNSW 索引；
  - 审批的 `begin immediate` 原子 claim 换成 `SELECT ... FOR UPDATE SKIP LOCKED`，语义不变；
  - 过渡期可先开 SQLite WAL 模式缓解读写互斥。
- 验收：evaluate_v3 的恰好一次门禁在并发压测（多 worker 同时批准同一草稿）下仍为 0 违规。

### 3. 真实 embedding 模型
- 现状：SHA-256 哈希 n-gram 64 维向量，只有"字符重合"意义上的相似度。
- 落地：BGE-m3 / text-embedding-3 类模型，异步批量生成（上传后入队，不阻塞请求）；保留现有 keyword 通道做 hybrid（BM25 + 向量 + RRF 融合）；embedding 版本号入库，支持灰度重建。
- 验收：构造 50 条以上中文问答评测集，hybrid Top-3 命中率显著高于现有基线后再切默认。

## P1：能力升级（决定回答质量上限）

### 4. LLM 抽取升级 GraphRAG
- 现状：正则规则抽取 8 类实体，换语料需要改规则。
- 落地：
  - 抽取层换 LLM 结构化输出（JSON Schema 约束，沿用现有 `GraphEntity/GraphRelation` 契约，存储与查询代码不用动）；
  - 实体消歧（同名归一、别名表）；
  - 图存储视规模决定：十万关系以内 PostgreSQL 递归 CTE 足够，之上再上 Neo4j + Cypher；
  - 保留规则抽取作为 LLM 不可用时的降级通道。
- 验收：evaluate_v4 换成人工标注的多文档评测集，实体/关系召回 ≥ 85% 再放开。

### 5. 状态机迁移 LangGraph
- 现状：显式 Python 函数状态机（Router → Planner → Retriever → Evidence → Graph → Tool → Answer → Reviewer），节点契约已独立。
- 落地：节点原样映射为 LangGraph node，`AgenticRagState` 即 graph state；换来 checkpoint 持久化（崩溃恢复）、条件边（重查/拒答分支声明式）、原生 streaming 和 human-in-the-loop interrupt（审批可挂起工作流而不是当前的"草稿+轮询"）。
- 验收：现有 77 个测试与五道门禁在迁移后全绿，这正是当初留门禁的目的。

### 6. Router / Planner LLM 化
- 现状：关键词规则分类与改写，遇到语料外表述会漏。
- 落地：小模型（如 deepseek-v4-flash 低温度）做意图分类与 query 改写，规则版留作降级；工具选择从关键词触发升级为原生 function calling，工具 JSON Schema 已备好（`get_tools_for_llm()`）。
- 验收：分类准确率在扩充评测集上 ≥ 95%，且成本面板显示单次请求新增 token 可控。

## P2：规模与运维（用户量上来之前做）

### 7. 异步化与任务队列
- 文档解析、embedding、图谱重建改 Celery/ARQ + Redis 队列，上传接口只负责落盘与入队；`/chat` 改 SSE/WebSocket 流式输出（LangGraph streaming 顺带解决）。

### 8. 可观测性接轨标准
- 现有 trace 结构（name/status/detail）映射 OpenTelemetry span，接 Grafana/Jaeger；chat_metrics 汇总改 Prometheus 指标导出；成本面板从"每请求估算"升级为对账（供应商账单 API 定期校准单价）。
- 现有 chat_logs 回放保留——它是评测集的原料：负反馈样本定期导出 → 人工标注 → 回灌 evaluate 数据集，形成"线上失败 → 离线门禁"的飞轮。

### 9. 部署与交付
- Docker Compose：api + web + postgres + redis + worker（+ neo4j 可选）；CI 跑 `pytest + evaluate_v2~v5 + tsc + vite build`（脚本已是 exit code 门禁，接 GitHub Actions 只是包一层）；配置全部走环境变量，密钥进 secret manager，`.env` 只留本地开发。

### 10. 安全加固清单
- 上传：文件大小/类型白名单已有，补充内容嗅探与病毒扫描钩子；
- 审计：`_audit_payload` 已做大小截断，补充敏感字段脱敏规则（手机号/邮箱正则）；
- 审批：高风险工具（未来的发邮件/改库）要求二人审批与操作理由；
- 限流：按租户 QPS 与 token 预算双重限流，预算超限时降级 local 模式（现有 auto 降级链路可复用）。

## 不建议做的事

- 不要在语料没上规模前先上 Neo4j——BFS + SQLite 在当前量级快且零运维，图数据库的收益从多跳复杂查询和十万级关系才开始。
- 不要跳过评测集直接换真实 embedding/LLM 抽取——没有基线对比的"升级"无法证明没有回退，这套项目的核心方法论就是门禁先行。
- 不要把 chat_metrics 与 chat_logs 合表——指标表不含原文是刻意的隐私分层，生产上还要给 chat_logs 加保留期（如 30 天）与脱敏导出。

## 落地顺序建议（一句话版）

```text
鉴权/租户 → PostgreSQL+pgvector → 真实 embedding（带评测集）
→ LangGraph 迁移 → LLM 抽取图谱 → 流式+队列 → OTel 观测 → Docker/CI 全家桶
```

每一步都以"77 测试 + 五道门禁全绿"为回归标准，门禁指标随能力升级同步收紧（例如 embedding 升级后把 V2 的 P95 门槛从 100ms 调整为含模型调用的 SLA 口径）。
