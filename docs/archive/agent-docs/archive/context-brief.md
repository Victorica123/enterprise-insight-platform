# Context Brief

> 用途：新对话或上下文丢失时，优先给 AI 看这份短文件。长文档只在需要查细节时再打开。

## 项目

```text
企业智能工单与知识助手平台
路径：D:\multi agents
阶段：V1-V5 全部收口（问答 / Agentic RAG / 工单审批 / GraphRAG / 观测成本）
目标：知识检索与证据回答 -> 图谱关系链 -> Tool Agent -> 写操作审批 -> 工单执行 -> 审计、token 成本与反馈闭环
```

## 当前能力

- 后端：FastAPI，路径 `apps/api`。
- 前端：React/Vite，路径 `apps/web`。
- 存储：SQLite，路径 `apps/api/data/knowledge_base.sqlite3`。
- 文档：支持 `.txt`、`.md`、文本型 `.pdf`。
- PDF：优先 PyMuPDF，回退 pypdf；中文 PDF 已做基础清洗。
- 回答模式：`local`、`api`、`auto`。
- LLM：支持 DeepSeek / OpenAI 兼容 API，本地配置在 `apps/api/.env`，不要打印 key。
- Trace：`/chat` 返回 query 扩展、检索、来源选择、证据检查、回答路径。
- Evidence Check：根据问题类型动态判断证据强度，不足则拒答。
- Retriever：已拆出 `apps/api/app/retrievers.py`，支持 `keyword` / `embedding` / `hybrid`。
- Embedding 管理：支持查看向量覆盖率和一键重建本地 embedding。
- 系统状态：支持 `/system/status`，前端显示 API、文档、chunk、LLM 配置状态。
- 前端交互：支持复制回答、清空回答、关闭错误提示、上传/删除/重建后自动刷新状态。
- 工作流：支持 `standard` / `agentic` 切换，agentic 默认开启。
- Agentic RAG：Router、Planner、Retriever、Evidence、Answer、Reviewer 六节点状态机。
- 防幻觉：复杂问题自动第二轮；弱证据重查；主题不匹配拒答；返回前审核引用。
- 前端摘要：展示意图、复杂度、检索轮数、query、证据状态、引用状态和参与节点。
- 工程指标：`GET /metrics/summary`，前端展示回答率、拒答率、P95 延迟、平均轮次、证据和引用状态。
- 评测：`scripts/evaluate_v2.py` 提供固定数据集、质量指标和发布门槛。
- V3 工单系统：内置工单表（tickets + pending_actions），支持 CRUD。
- V3 工具调用：Tool Registry 4 个工具（查询/创建/更新工单），Tool Agent 自动判断调用。
- V3 Human-in-the-loop：写操作生成待审批草稿，批准后执行，前端一键审批。


## 关键文件

```text
apps/api/app/main.py              API 装配入口（健康/文档/chat）
apps/api/app/routes/              embedding/观测/图谱/工单路由
apps/api/app/rag.py               RAG 主流程
apps/api/app/agentic_rag.py       V2 Agentic RAG 状态机（含 V4 Graph Agent 接入）
apps/api/app/retrievers.py        检索器抽象层
apps/api/app/database.py          SQLite 持久化（含 V5 chat_logs）
apps/api/app/document_parser.py   txt/md/pdf 解析
apps/api/app/llm.py               DeepSeek/OpenAI 调用 + usage 采集
apps/api/app/llm_client.py        共享客户端、超时/重试/token 预算
apps/api/app/local_answer.py      本地规则回答与字段抽取
apps/api/app/agent_planning.py    Agent 规则路由/检索规划降级
apps/api/app/citation_review.py   引用修复与声明检查
apps/api/app/models.py            Pydantic 模型
apps/web/src/main.tsx             前端应用壳与状态编排
apps/web/src/features/            QA/工单/图谱/监控 feature
apps/web/src/api.ts               前端 API 请求
apps/web/src/styles/              base/qa/tickets/graph-monitor 样式域
apps/api/app/ticket_store.py      V3 工单存储
apps/api/app/tools.py             V3 工具调用层
apps/api/app/graph_store.py       V4 图谱抽取与存储
apps/api/app/graph_rag.py         V4 Graph Agent
docs/project-report.md            项目总结报告（架构/工作流/指标可视化）
docs/engineering-optimization.md  工程化落地优化路线
docs/troubleshooting-log.md       错误记录 + 设计知识库
docs/v1-task-list.md              阶段任务清单
```

## 启动

```powershell
cd "D:\multi agents\apps\api"
uvicorn app.main:app --reload --port 8000
```

```powershell
cd "D:\multi agents\apps\web"
npm run dev
```

访问：

```text
后端：http://127.0.0.1:8000/docs
前端：http://127.0.0.1:5173
```

## 验证

```powershell
cd "D:\multi agents"
.\scripts\context-harness.ps1 -Mode verify
```

## Harness

```powershell
.\scripts\context-harness.ps1 -Mode brief
.\scripts\context-harness.ps1 -Mode files
.\scripts\context-harness.ps1 -Mode verify
```

## 下一步

1. V1–V5 闭环 + A/B 深挖 + P1/P2 工程瘦身已落地：77 个自动化测试 + V2/V3/V4/V5/V6 五道离线门禁通过。
2. 生产化路线（鉴权、pgvector、LangGraph、Neo4j、队列、OTel）见 `docs/engineering-optimization.md`。

## 2026-07-21 V2 完成点

已完成：

- 新增 `apps/api/app/agentic_rag.py`，实现 Router、Planner、Retriever、Evidence、Answer、Reviewer 六节点状态机。
- `/chat` 新增 `workflow_mode=standard|agentic`，默认 `agentic`。
- 实现问题分类、query 改写、复杂问题拆解、最多两轮检索、动态证据检查和引用审核。
- 新增主题锚点门控，修复无关问题被本地 embedding 虚高分误判的问题。
- 前端新增工作流切换和 Agentic 执行摘要。
- 新增 Agentic、API 契约和指标测试，12 个测试全部通过。
- 新增 API 契约测试，standard 模式保持兼容，agentic 返回完整摘要。
- 新增运行指标持久化、`/metrics/summary` 和前端工程指标面板。
- 新增离线评测脚本，覆盖分类、答/拒、轮次、引用和延迟门槛。
- 修复上传后原生文件选择器未清空、模式切换后旧答案残留、空问题仍可点击等交互问题。
- Python 编译、12 个测试、TypeScript 检查、Vite production build 均通过。
- 当前 4 个基准 HTTP 请求：回答率 75%、正确拒答率 25%、错误率 0%、引用就绪率 100%、平均轮次 1.5、P95 约 5 ms。
- FastAPI 与 Vite 已启动，后端/前端 HTTP 均返回 200，服务日志无错误。
- 真实 SQLite 数据验证：简单问题一轮通过、复杂问题两轮通过、无关问题 `topic_mismatch` 拒答。

环境说明：

- 自动浏览器控制仍受此前针对 `127.0.0.1:5173` 的安全限制，因此没有代替用户点击页面；API、构建、状态同步逻辑和服务运行均已自动验证。

快速验收：

```powershell
cd "D:\multi agents"
.\scripts\context-harness.ps1 -Mode verify
```

当前服务地址：

```text
前端：http://127.0.0.1:5173
API 文档：http://127.0.0.1:8000/docs
```

页面中依次验证：

```text
1. standard / agentic 可以切换。
2. “甲方客户A的项目为什么延期？”应一轮检索并通过。
3. “项目为什么延期，同时合同有什么风险？”应两轮检索并通过。
4. “火星基地的氧气供应方案是什么？”应两轮后 topic_mismatch 拒答。
5. Agentic 摘要显示意图、复杂度、轮次、query、证据、引用和 Agent 路径。
6. 最终回答包含 [来源 N] 标准引用。
```

## Token 节省规则

- 日常推进不再整段重写长交接文档。
- 新对话优先贴本文件，不贴完整 `session-handoff`。
- 查代码先用 `rg` 定位，再只读相关文件片段。
- 搜索文件时排除 `node_modules`、`dist`、`__pycache__`、数据库文件。
- 文档更新优先追加 1-3 行结论，设计细节只在确实新增机制时记录。
- 大文件只引用路径和关键行，不复制全文。

## 2026-07-22 V3 工程收口

已完成：

- 受控工具链：查询立即执行；创建/更新只生成 15 分钟草稿，批准后执行。
- 审批状态机：`pending -> executing -> succeeded/failed`，另有 `rejected/expired`。
- 原子 claim + `execution_count` 保证重复批准不重复写；等价未决草稿会去重。
- JSON Schema 风格参数校验、`viewer/operator/admin` 角色门控、输入大小限制。
- `tool_call_logs` 审计输入/结果/状态/角色/耗时；`GET /metrics/tools` 输出成功率、P95、审批率和重复执行违规。
- 直接查询/更新工单跳过 RAG，降低延迟和 token；知识型建单仍先过 Evidence Check。
- 前端支持角色切换、草稿审批、状态变更审批、工具指标和审计列表。
- `scripts/evaluate_v3.py` 门禁：7 项安全检查 100%、重复执行违规 0、工具 P95 <= 200 ms。
- 当前回归：18 个测试通过，V3 本次 P95 18.95 ms，前端 production build 通过。

## 2026-08-03 V4 + V5 工程收口

已完成：

- V4 GraphRAG：`apps/api/app/graph_store.py`（规则抽取 + SQLite 图存储 + BFS 链路）与 `graph_rag.py`（Graph Agent）。
- 实体 8 类（客户/项目/人员/合同/日期/原因/风险/工单），关系带证据句与文档溯源；字段连排的 PDF 文本自动补句界。
- 上传增量入图、删除自动重建、工单同步连边；`/graph/overview|entities|relations|paths|rebuild` 五个端点。
- Graph Agent 接入 agentic 状态机：关系/风险/因果/事实问题查 2 跳邻域，关系链与风险链注入回答并写 trace。
- V5 观测：`/chat` 返回 token_usage 与 log_id；API 模式记真实 usage 并按单价估算成本，local 估算规模、成本 0。
- chat_logs 请求日志（问题/结果/延迟/token/成本/trace）支持失败回放；`POST /chat-logs/{id}/feedback` 反馈闭环进满意度指标。
- 前端新增"关系图谱"（SVG 分层可视化 + 链路查询 + 关系明细）与"运行监控"（token 成本、延迟、日志回放、反馈）两个面板；回答区加 👍/👎 与 token 徽标。
- 门禁：`evaluate_v4.py`（实体/关系召回 100%、结构 6/6、图查询 P95 8.1ms ≤ 50ms）、`evaluate_v5.py`（观测 8/8、chat P95 29.7ms ≤ 300ms）；V2（P95 11.6ms）/ V3（P95 19.8ms）回归通过。
- 回归：77 个测试通过；`context-harness.ps1 -Mode verify` 串起编译、测试、冒烟、五道门禁与前端构建一次通过。
- 真实语料线上验证：图谱重建 10 实体 / 8 关系（24.7ms），"甲方客户A的项目为什么延期？"命中 Graph Agent，HTTP 延迟 25.4ms，链路 客户A→委托→项目→负责人→李四 可查。
- 工程化落地路线新增 `docs/engineering-optimization.md`（P0 鉴权/pgvector/真实 embedding，P1 LLM 抽取/LangGraph，P2 队列/OTel/部署）。
