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

如果只是修一个明确问题，读完本文后直接进入对应模块，不需要通读全部知识文档。

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
| 媒体任务状态、幂等和重试 | `services/media-service/.../workflow/` |
| 转写完成跨服务投递 | `services/media-service/.../integration/` |

### Agent Service

新增业务入口统一位于 `services/agent-service/app/architecture/`；它们组合下表中的实现模块，并保留旧导入路径供兼容测试使用。优先按全景层选择 façade：`orchestration.py`（对话）、`retrieval.py`（检索与证据）、`execution.py`（三层执行器）、`knowledge.py`（知识底座）、`governance.py`（审批与生命周期）、`observability.py`（观测与审计）。完整映射见 [ARCHITECTURE_PANORAMA.md](ARCHITECTURE_PANORAMA.md)。

| 要找的问题 | 入口 | 职责 |
| --- | --- | --- |
| 文档/chunk/摄取回执 | `database.py` | 核心知识持久化，不含聊天观测逻辑 |
| 问答指标、日志、反馈、历史引用 | `chat_observability_store.py` | 观测数据与回放 |
| 标准/Agentic RAG | `rag.py`、`agentic_rag.py` | 工作流编排与回答 |
| 授权检索和缓存 | `retrievers.py`、`embeddings.py` | 模型看到证据前的 scope 过滤 |
| 六阶段分析 | `analysis_evidence.py`、`analysis_pipeline.py`、`analysis_store.py` | 冻结证据、阶段执行与恢复 |
| PRD 发布和派生交付物 | `publication_service.py`、`publication_artifacts.py` | 审批状态与交付物投影 |
| 知识版本与替代/撤回 | `knowledge_lifecycle_store.py` | 版本物化、CAS 与原子回滚 |
| 图谱抽取规则 | `graph_extraction.py` | 纯文本到实体/关系，不访问数据库 |
| 图谱存储和重建 | `graph_store.py`、`graph_rag.py` | 持久化、失效和查询 |
| 工单与待审批动作 | `ticket_store.py` | 工单、审批状态与恰好一次领取 |
| 受控工具执行 | `tools.py` | 工具注册、策略校验与执行编排 |
| 工具审计与指标 | `tool_observability_store.py` | 调用日志、状态统计与时延指标 |

### React Web

`apps/web/src/api.ts` 是兼容入口；新增代码应优先进入领域模块：

- 通用请求/JWT：`apiClient.ts`
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
- `evaluate_v2.py`～`evaluate_v5.py`：历史评测演进；当前合并门禁以 V6、PRD V1 和 Knowledge Lifecycle V1 为主。

## 完成修改前

至少运行改动模块的聚焦测试、`python scripts/update_knowledge.py --check`，再按 `skills/enterprise-insight-maintainer/references/maintenance-workflow.md` 判断是否需要服务级或平台级验证。不要为了减少文件数把身份、审批、证据、契约或质量门禁重新揉回一个大文件。
