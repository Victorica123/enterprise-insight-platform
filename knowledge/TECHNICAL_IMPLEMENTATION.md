# 技术实现详解

本文解释 Enterprise Insight Platform 如何从视频与文档形成可验证洞察，并说明代码框架、关键数据流、Agent/RAG、缓存、权限、可靠性和本地验收。它描述当前已实现事实，不把可选生产组件写成已上线能力。

## 1. 总体框架

系统由三层组成：统一交互层、两类业务后端和独立的工程知识维护平面。

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
       └─ knowledge and controlled action tools

Engineering knowledge plane (not customer runtime data)
  Codex Skill -> semantic Top-K router -> generated knowledge index -> source documents
```

选择两个后端而不是强行合成一个服务，是因为媒体处理和 Agent 分析拥有不同的状态机、吞吐特征和失败恢复方式。两个服务共享身份与契约，不共享数据库；React 只在展示层聚合状态。

## 2. 目录和模块职责

| 路径 | 技术与职责 |
| --- | --- |
| `services/media-service` | Spring Boot、Spring Security、JPA、H2/MySQL；拥有账号、Workspace、上传、播放、媒体任务、转写和 outbox。 |
| `services/agent-service` | FastAPI、Pydantic、SQLite；拥有证据、检索、分析、PRD、审批、知识、图谱、工单和评测。 |
| `apps/web` | React 19、TypeScript、Vite；统一登录、Workspace 管理、媒体、分析、图谱、工单与监控工作台。 |
| `contracts` | 跨服务 JSON Schema 与事件/HTTP 数据结构；用于先契约、后实现。 |
| `knowledge` | 人工维护的产品、架构、安全、Agent、运维、质量事实及 ADR。 |
| `scripts` | localhost 全链路验收、备份恢复、知识快照和语义索引。 |
| `skills/enterprise-insight-maintainer` | 项目专用维护 Skill、语义检索入口和渐进式参考资料。 |

## 3. 核心业务纵向链路

### 3.1 视频到证据

1. 浏览器携带 Media Service 签发的 active-Workspace JWT。
2. Spring Security 将受信 claims 重建为 `WorkspacePrincipal`，后续代码不读取客户端自报角色头。
3. 上传服务把文件写入租户范围内的媒体目录，同时创建持久化媒体任务。分片、直传和普通上传都绑定 tenant、owner 与上传会话。
4. 媒体任务完成后生成结构化转写片段，每段带稳定 segment ID、开始/结束毫秒、说话人和文本。
5. Media Service 在业务事务内写入 `transcript.ready.v1` outbox；调度器异步投递，瞬时错误指数退避，契约冲突进入 DEAD。
6. Agent Service 使用 `event_id` 和 `tenant_id + asset_id + transcript_version` 两级幂等摄取；同版本不同内容返回 409，不覆盖旧事实。
7. 文本分块后同时写入确定性 hash embedding，并在本地 BGE 可用时写入 `embedding_v2`；时间戳和媒体身份一直随 chunk 保留。

### 3.2 证据问答

1. Agent Service 从 JWT 得到 `tenant_id`、`owner_id` 和 `workspace_type`。personal 查询绑定 tenant + owner，team 查询绑定 tenant；过滤发生在检索前。
2. Router 判断问题意图与复杂度，Planner 生成原问题、改写和补充 query。
3. Retriever 可选择 keyword、embedding 或 hybrid。hybrid 使用 RRF 合并排名，再用关键词/向量归一化分执行证据门控；可选 cross-encoder 只重排 Top-12 候选。
4. Evidence Agent 判断证据是否足够；复杂问题最多进行受限轮次补查，不无限循环。
5. 本地模板或 LLM 生成答案后，引用校验器检查 source、租户归属及视频时间范围。无法支持的结论必须标记假设或拒答。
6. 前端点击视频引用时向 Media Service 请求短时播放 token；Agent Service 不保存对象存储凭证。

### 3.3 六阶段分析和发布治理

分析流程按意图、干系人、领域、风险、收敛、PRD 六个可观测阶段执行。阶段之间传递结构化 Pydantic 状态，而不是依赖不可检查的长对话。

证据不足时，会话进入 `WAITING_CONFIRMATION` 并保存检查点和恢复 token；用户补充后从收敛点继续。PRD 从 `DRAFT_READY` 进入 `PUBLISH_PENDING` 后：

- personal Workspace 由 OWNER 使用一次性 token 做第二次明确确认；
- team Workspace 必须由不同的写成员批准，提交者不能自批；
- compare-and-set 状态、审计、canonical JSON SHA-256 版本、知识候选和行动草稿在同一 SQLite 事务提交；
- 知识发布和外部工单仍有各自独立审批，PRD 通过不等于副作用自动执行。

### 3.4 Workspace 协作

Media Service 是成员关系和 active Workspace 令牌的唯一权威。OWNER 创建团队，OWNER/ADMIN 生成 15 分钟一次性邀请，服务端只保存邀请码 SHA-256；用户接受后默认成为 MEMBER。角色映射为 VIEWER→viewer、MEMBER→operator、ADMIN/OWNER→admin。

切换 Workspace 时服务端重新查询成员关系并签发新 JWT。团队资源按 tenant 共享，个人资源按 tenant + owner 隔离；`owner_id` 在团队中仍用于创建者归属和审计，而不是缩小团队读取范围。

## 4. Embedding、混合检索和缓存

### 4.1 业务 RAG 向量

业务 Agent 有两套向量表示：

- `embedding`：64 维确定性字符 n-gram feature hashing，无下载、离线可复现，是功能保底。
- `embedding_v2`：可选 `BAAI/bge-small-zh-v1.5` 本地 ONNX 向量；模型不可用时不会阻断摄取和检索。

真实模型惰性加载并支持显式 warm-up。新增的向量缓存以 `(model object identity, SHA-256(text))` 为 key，value 是不可变向量 tuple：同一 batch 的重复文本只推理一次，跨请求重复文本命中最大 512 项的进程内 LRU。key 不保存原始文本，降低缓存扩大敏感信息驻留面的风险。

文档 chunk 快照另有一个最大 64 项的 LRU，key 包含数据库路径、持久化 `content_revision`、tenant、owner 和 asset 范围。任何摄取或重建都会提升 revision，因此多进程写入也能让旧快照自然失效，不需要依赖“当前进程记得清缓存”。

### 4.2 维护 Skill 语义索引

维护知识和客户业务数据完全分离。`scripts/knowledge_index.py` 只扫描仓库内批准的知识、ADR、契约、README、当前运维文档和 Skill 参考，不读取 `docs/archive`、SQLite、媒体、上传内容或 runtime 目录。

索引使用 192 维 `hash-ngram-topic-embedding-v1`：英文/代码词、中文 1~3 gram 与领域 topic alias 共同映射到稳定向量。归一化向量进一步量化为 signed int8 并 Base64 存储，把每个 chunk 的向量载荷固定为 192 字节；查询时解码并执行 cosine。它不需要模型下载，适合提交到 Git 和 CI 重建；它的目标是把维护任务路由到正确文档，不替代业务侧 BGE 语义模型。

缓存分四层：

| 层级 | Key | Value | 失效方式 |
| --- | --- | --- | --- |
| 文档向量增量复用 | chunk 内容 SHA-256 + 算法版本 | 192 维维护向量 | 内容、算法或维度变化 |
| 维护查询缓存 | corpus revision + query digest + Top-K | 文件、标题、行号和分数 | 任一受索引文件、分块版本或向量算法变化 |
| 业务 chunk 快照 | DB path + content revision + scope | 已授权 chunk 对象 | 数据写入提升 revision |
| 业务真实向量 LRU | model identity + text digest | BGE 向量 | 进程重启、显式清理或 LRU 淘汰 |

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
- 可恢复状态机：媒体任务可重试；Agent 会话可从 checkpoint 恢复；审批副作用独立治理。
- 不可变发布：canonical JSON + SHA-256，发布版本不可覆盖。
- 证据最小化：跨服务事件不携带 JWT、存储密钥或永久播放 URL。
- 轻重模式分离：localhost mock/local 模式用于无外部依赖验收，不能代替 Redis、MQ、对象存储和真实模型 smoke。

## 7. 前端实现

React 应用只保存一个 active Workspace session。切换后覆盖本地 JWT/session，并清空文档、工单、工具调用、聊天响应和选中媒体等 scope 相关状态；Analysis 与 Graph 使用 tenant key 强制重建，防止旧 Workspace 组件状态串入新空间。

Workspace 管理弹窗通过 React Portal 挂载到 `document.body`。这是因为 sticky header 的 `backdrop-filter` 会创建新的 containing block，使嵌套的 `position: fixed` 相对 header 而非 viewport 定位。真实浏览器测试在 1280×720 下捕获并验证了该问题。

## 8. 验证体系

- Media Service：JUnit/Spring 集成测试覆盖认证、上传、任务、播放、outbox、租户与团队协作。
- Agent Service：unittest/pytest 覆盖摄取、检索、向量回退、分析、发布、工具、隔离与观测。
- Agent 评测：黄金集分别验证 keyword、embedding、hybrid 的决策、recall@3、事实正确性和延迟门禁。
- Web：TypeScript project build + Vite production build，并补真实浏览器业务操作。
- 平台：`scripts/local_acceptance.py` 使用随机 localhost 端口、H2、SQLite、本地文件和 mock AI 跑双用户完整纵向链路。
- 知识：生成器漂移检查、维护索引单元测试和 Skill quick validation。

## 9. 面试或简历可重点说明的技术价值

1. 不是把两个页面拼在一起，而是用统一身份、tenant/owner、版本化契约和一条业务纵向链路完成系统整合。
2. RAG 不只“有向量库”：检索前授权、混合召回、RRF、可选 rerank、证据门控、引用验证和时间戳回放形成可信链。
3. Agent 不是一次大 Prompt：六阶段结构化状态、等待/恢复、CAS 审批、不可变版本和受控工具把不确定生成与确定性副作用分开。
4. 可靠性不是只靠重试：transactional outbox、双重幂等、冲突保留旧事实、指数退避和可恢复检查点共同保证一致性。
5. 缓存不是盲目存结果：所有缓存 key 都带模型/内容/数据 revision 或授权 scope，并明确缓存层和失效边界。
6. 工程知识也可执行：Skill、语义索引、ADR、生成快照和 CI 漂移检查让后续 Agent 不必每次重新理解整个仓库。

## 10. 后续生产优化顺序

1. 先确定正式 IdP、JWT 即时撤权、数据保留期限和模型数据策略，这些会改变安全架构。
2. 用真实 MySQL、Redis、RocketMQ/S3 兼容对象存储跑集成与故障注入，再给出生产可靠性声明。
3. 当业务 chunk 数量超过单机扫描预算时，再引入支持 metadata pre-filter 的向量数据库；迁移前保留当前 SQLite 基线做行为对照。
4. 为 embedding LRU 和检索快照增加命中率、淘汰、冷启动耗时指标，并依据真实流量调整容量。
5. 模型供应商支持 prompt caching 时，固定 system/tool schema 前缀，动态证据后置，并以 provider 返回的 cached-token 指标验证收益。
