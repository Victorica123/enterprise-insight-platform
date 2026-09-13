# 智能体技术架构全景与本项目映射

本文把仓库中的架构实现与 `docs/images/architecture-panorama.png` 所示的“智能体技术架构全景”逐层对照。图片提供的是目标能力地图；本文只把已经存在的代码和经过测试的边界标为已实现，不把模块名称包装成已经部署的外部基础设施。

## 全景分层

```text
React 用户入口 / Chat / Admin / 文档 / 观测
                 │
         对话编排中心（Agent Service）
                 │
       检索与证据 ── 三层执行器
                 │          │
             知识底座 ── 工具与扩展
                 │
     Redis / Kafka / Trace / 审批 Hook（工程护栏）
```

| 图片层 | 当前 façade | 现有实现 | 真实状态 |
| --- | --- | --- | --- |
| 对话编排中心 | `app.architecture.conversation` / `orchestration` | JSON/SSE 共用流水线、主题记忆、计划链、注册表、受限补查与分析检查点 | 已实现；复用成熟执行器，记忆不能替代新证据 |
| 检索与证据 | `app.architecture.retrieval` | 授权范围过滤、关键词/向量/混合召回、RRF、可选 Top-12 rerank、引用和 provenance 校验 | 已实现；当前以 SQLite 扫描基线承载，尚非独立向量数据库集群 |
| 三层执行器 | `app.architecture.execution` | 六阶段确定性领域 specialist、Agentic RAG、受审批工具执行 | 已实现；specialist 是有界规则执行器，不冒充自治多 Agent Runtime |
| 知识底座 | `app.architecture.knowledge` | 文档解析/分块、视频转写事件摄取、embedding、图谱索引、知识生命周期 | 已实现；PGVector/Elasticsearch/Neo4j 只对应可替换适配方向 |
| 治理与审批 | `app.architecture.governance` | PRD 发布、知识候选与生命周期、行动项、审计、CAS 检查点 | 已实现；写操作和知识发布保留人工门禁 |
| 工程化护栏 | `app.architecture.observability` + 配置/存储模块 | Settings、编号迁移、会话续租/预算/取消、JWT scope、revision、outbox、审计与保留 | 本地回归已验证；真实 MySQL、多实例与外部模型需独立验证 |

## 端到端请求路径

1. React 通过统一 API 入口把请求送到 Media Service 或 Agent Service；服务端从共享 JWT 得到 tenant、owner、workspace 和 role。
2. Chat 路由创建 `RetrievalScope`，由 `ConversationOrchestrator` 先跑 `PreparationChain` 生成 `ExecutionPlan`，再由 `ExecutorRegistry` 按 `plan.mode` 选择单一执行器（clarify / tool_only / retrieval / agentic；`workflow_mode` 只是输入）。整个计划与执行在一个每请求调用预算内运行（模型调用 8 次、工具调用 6 次，超限降级为规则 / 模板并写 trace）。scope 在检索前生效，不能由问题正文或客户端角色头覆盖。
3. 检索层执行混合召回和证据门控；按分数选出的来源再经字符预算裁剪（单来源 2200、总量 5200 字符），模型、证据检查与引用审核看到同一份证据。视频来源继续携带 `asset_id`、`segment_id`、`start_ms` 和 `end_ms`，无法验证的结论拒答或标记为缺口。
4. 分析请求先固化授权证据快照，再按六阶段运行。缺少决策人、验收标准或冲突处理方式时进入 `WAITING_CONFIRMATION`；确认通过 CAS 恢复，不重写阶段 1–4。
5. PRD、知识候选和行动项分别经过人工审批。批准知识会物化为带 provenance 的受治理文档，工具副作用只产生待审批 action，不在问答期间直接执行。
6. 观测层记录请求、回答状态、引用状态、token、工具调用、影子路由一致性和审计事件，供 `/metrics/*`、`/chat-logs` 和管理面板使用。

## 模块化迁移约定

`services/agent-service/app/architecture/` 是新的应用边界，不立即搬迁所有大型实现文件。旧模块继续作为 persistence/algorithm adapter，并保持原导入路径，避免一次性破坏已有契约和评测。新功能应优先从以下入口进入：

- `context.py`：从已验证 principal 构造不可变请求上下文；
- `conversation.py`：JSON/SSE 共用会话、记忆、租约与计量流水线；
- `orchestration.py`：执行计划链（`planning.py`）+ 执行器注册表，按 `plan.mode` 选择 clarify / tool_only / retrieval / agentic；
- `retrieval.py`：检索、图谱和证据 provenance；
- `execution.py`：分析、Agentic RAG 与受控工具；
- `knowledge.py`：文档及媒体知识摄取；
- `governance.py`：发布、生命周期、行动项和检查点；
- `observability.py`：聊天/工具指标与审计。

这些 façade 不拥有数据库表，也不改变两个后端服务的职责。Media Service 仍拥有媒体生命周期，Agent Service 仍拥有知识与分析生命周期。

所有 routes 的业务导入已收口到 façade，身份、配置与 DTO 是明确基础例外。DDL 位于编号 `schema/`，配置只从 `config.py` 读取；图算法与工单纯规则已从 store 分离。授权相邻块扩展遵循主题与预算，向量双写 blob/JSON 并有界后台补齐。会话累计模型 40 / 工具 30，默认 120 秒租约续期，SSE 只有 `done` 为最终引用审核结果。决策见 ADR-0016/0017。

## 生产边界与后续替换

- 当前测试和本地验收使用 SQLite、进程内缓存和 mock/local 模式；它们是可重复的基线，不等于 Redis、Kafka、PGVector、Elasticsearch、Neo4j 或对象存储已经部署。
- 当数据规模超过 SQLite 扫描预算时，可在 `retrieval.py` 后增加支持 metadata pre-filter 的向量/关键词适配器，并以现有检索评测作为行为对照。
- MCP/Skills、联网搜索和 Checkpoint 是扩展点：工具必须注册定义、通过 tenant/role 校验并在产生副作用前进入审批；不能因为架构图列出了能力就绕过治理。
- 真实生产声明仍需 MySQL、Keycloak、Redis、消息系统、对象存储和模型供应商 smoke 证据，以及故障注入和恢复数据支持。

机器可读映射见 `services/agent-service/app/architecture/manifest.py`，边界回归见 `services/agent-service/tests/test_architecture_boundaries.py`。
