# Enterprise Insight Platform 面试讲解指南

本文只使用仓库中已实现、已测试或明确标注为边界的事实。不要把 mock、候选 SLO 或规划描述成生产结果。

## 一分钟项目介绍

> 我做的是一个面向客户访谈和需求评审的企业多模态洞察平台。用户上传会议视频后，Media Service 负责可靠处理并产出带时间戳的转写证据，通过事务 outbox 幂等进入 Agent Service。Agent 在检索前完成 tenant/owner 授权过滤，再通过混合召回、证据门控和引用校验回答问题。复杂需求进入六阶段分析；信息不足时持久化等待人工补充，最终生成证据化 PRD。PRD、知识和行动项分别有人工审批：团队空间要求不同成员四眼审批，批准知识会带 PRD 版本、内容哈希和原始证据进入未来 RAG，行动项批准后才创建工单。整条链路可以用 25 项 localhost 自动验收复现，不依赖服务器、域名或外部模型。

## 为什么这是一个产品而不是两个项目

- 一个 React 工作台、一个登录态和一个 active Workspace。
- Media Service 是账号、成员关系、媒体生命周期和播放授权的权威。
- Agent Service 是证据、分析、PRD、知识和行动项生命周期的权威。
- 两个服务共享 JWT/tenant/owner 语义与版本化事件，但不共享数据库。
- 用户旅程从上传一直延伸到知识和行动，而不是在两个系统之间手工搬运数据。

## 最值得展开的五个工程问题

### 1. 如何防止 RAG 越权

不是“检索后删掉别人的结果”，而是把 `tenant_id`、personal owner 和可选 asset scope 放进数据库查询及 Chunk 缓存 key。模型只接触已经授权的数据。team 读取按 tenant 共享，personal 读取按 tenant + owner 私有。

追问准备：为什么 team 仍保留 `owner_id`？用于创建者归属、审计和职责分离，不用于缩小团队读取范围。

### 2. 如何保证视频证据可信

转写片段保存稳定 asset/segment ID、`start_ms/end_ms` 和说话人。Agent 来源不保存永久播放 URL；前端点击引用时再向 Media Service 申请短时播放授权。最终答案会校验视频范围，不能伪造不存在的引用。

### 3. 为什么使用事务 outbox 和双重幂等

Media 在业务事实提交的同一事务写 outbox，避免“任务成功但事件丢失”。Agent 既按 `event_id` 防重复投递，又按 tenant + asset + transcript version 防语义重复；同版本不同内容返回冲突并保留旧事实。这里保证的是可恢复的 at-least-once，不虚构全链路 exactly-once。

### 4. Agent 为什么不是一个大 Prompt

六个阶段传递结构化 Pydantic 状态。证据不足时进入 `WAITING_CONFIRMATION`，保存一次性 resume token；补充后从检查点恢复。生成模型只负责不确定内容，权限、状态转换、哈希、幂等和副作用由确定性代码控制。

当前实现通过 HTTP + 持久化检查点恢复，不是 WebSocket/AppServer；如果被问到实时交互，应明确这是下一层传输优化，不影响恢复语义。

### 5. “知识自进化”到底落在哪里

PRD 发布只生成 `PENDING` 候选，不能自动改共享知识。候选再次通过 personal OWNER 或 team 不同成员决定后，系统在同一事务中：

1. compare-and-set 候选状态；
2. 生成包含原始证据和治理来源的规范知识文档；
3. 保存 PRD version、candidate ID 与 SHA-256；
4. 生成 embedding、提升 content revision 并建立图谱索引；
5. 后续授权 RAG 返回 `origin_type=approved_knowledge` 的来源。

如果图谱或索引失败，候选状态和知识文档一起回滚。批准知识不能通过普通文档删除接口绕过审计。

工程维护 Skill 是另一条独立链路：它只索引仓库知识与 ADR，不读取客户数据。不要把业务知识库和 Codex Skill 索引混为一谈。

## 高频追问与回答骨架

### 为什么保留两个后端服务

媒体任务与 Agent 分析是不同状态机：前者偏大文件、外部 I/O、排队和重试，后者偏检索、模型、人工确认和审批。合成一个服务会耦合扩缩容、失败恢复和数据所有权；拆分后用身份与契约统一，而不是共享表。

### 为什么不是直接使用向量数据库

当前数据规模下 SQLite + hash/BGE 双向量能提供可重复基线，且便于测试授权过滤。只有 Chunk 规模超过单机扫描预算，才迁移到支持 metadata pre-filter 的向量数据库；迁移前保留当前黄金集做行为对照。

### hybrid 检索怎么做

keyword 与 embedding 独立召回，RRF 融合相对排名；证据门控仍使用两路归一化绝对分，避免“只有一个结果所以排名第一”被误判为强证据。可选 cross-encoder 只重排 Top-12，默认关闭。

### 缓存如何防止脏数据和越权

- BGE LRU key：model identity + 文本 SHA-256。
- Chunk LRU key：DB path + 持久化 content revision + tenant/owner/asset scope。
- 写入提升 revision，使其他进程读取时自然失效。
- 指标只在已登录 Embedding 状态接口暴露，公开健康状态不泄露流量。

### 团队审批怎么防止自批

Workspace 类型和角色来自 Media Service 根据成员表重新签发的 JWT。团队发布和知识批准都校验 `requested_by != approved_by`；跨租户返回 404 防止资源枚举。状态 CAS、审计和不可变版本在同一事务提交。

### 模型挂了怎么办

真实 embedding 不可用时回退确定性 hash embedding；LLM 未配置时仍能使用本地模板查看事实、证据和状态。降级保证系统可用，不代表本地模板具有真实模型质量。

### 如何证明不是 happy path Demo

- Agent Service 119 个测试；Media Service 108 个测试。
- keyword / embedding / hybrid 三路黄金集门禁。
- 25 项双用户 localhost 纵向验收。
- tenant/owner 负向用例、四眼审批、事务回滚、重复事件与冲突用例。
- Web 类型与生产构建、知识漂移检查和 CI 分故障域 job。

### 生产瓶颈会在哪里

优先看媒体 worker/外部转写配额、队列最老消息年龄、数据库连接、Chunk 扫描规模和模型延迟。MQ 只能削峰，不能降低单任务成本；缓存命中率必须按实例和代表性流量解释。

### 正式上线前还缺什么

正式 IdP 与即时撤权、数据/媒体保留期限、外部模型数据策略、版本化数据库迁移、统一平台真实中间件 smoke、Prometheus/OTel 聚合告警、备份恢复演练和基于真实流量批准的 SLO。

## 面试缺漏自查

| 面试官想确认什么 | 当前证据 | 回答边界 |
| --- | --- | --- |
| 你解决了什么业务问题 | 视频/文档到证据、PRD、知识、工单的一条用户旅程 | 尚无真实客户节省工时数据，只能讲目标价值，不能编造 ROI |
| 你个人做了什么 | 契约、两后端整合、统一前端、授权 RAG、Agent 状态机、验收和知识维护 | 区分原媒体能力、迁移整合与本轮新增能力，不把团队或模型产出全部说成手写 |
| 最难的工程问题 | 检索前授权、outbox 双幂等、等待恢复、四眼审批、知识原子物化 | 选择一到两个展开，不罗列所有技术名词 |
| 为什么这样选型 | 两类状态机保留两个服务；当前规模用 SQLite/BGE 基线；副作用用确定性事务治理 | 说明替代方案与触发迁移的条件，不说“这是最佳实践所以用了” |
| 如何证明正确 | 119 Agent、108 Media、三路黄金集、25 项 localhost、浏览器截图与负向用例 | mock/local 证明链路，不证明真实模型质量和生产吞吐 |
| 出过什么问题 | sticky header 造成 fixed 弹窗越界；知识批准曾只有状态没有未来召回；缓存需把授权 scope 纳入 key | 讲发现方式、根因、修复和回归测试，形成真实工程故事 |
| 如何上线和排障 | trace、状态机、outbox、监控、备份恢复手册和分故障域 CI | 正式 IdP、迁移、告警、灾备与真实中间件统一 smoke 仍是上线缺口 |
| 和实习经历有什么关系 | 方法论延续：六阶段、等待恢复、知识治理、可观测和人机边界 | 不宣称复刻公司内部 AppServer/WebSocket 或使用了公司代码 |

面试前至少准备三个可复述故事：一个业务闭环、一个失败/修复、一个取舍/边界。每个故事都按“背景 → 约束 → 选择 → 验证 → 仍未解决”讲，避免只背架构名词。

可直接计时练习的一分钟口述、8 分钟逐段话术、三段完整故事和追问速答见 [`INTERVIEW_REHEARSAL.md`](INTERVIEW_REHEARSAL.md)。

## 简历叙事如何保持真实

可以强调方法延续：六阶段拆解、人工补充与恢复、知识治理、权限/SLA/可观测性，以及把不确定生成和确定性副作用分离。

不要说：

- 个人项目复刻了公司的 Codex AppServer 或 WebSocket 架构；当前没有该传输层。
- localhost mock 结果代表真实模型质量或生产吞吐。
- 系统已经拥有线上用户、正式 SLA 或任意规模能力。
- Skill 会自动把所有坏案例写成规则；当前需要证据、人工决定和维护门禁。

建议说：

> 我把实习中形成的 Agent 工程方法迁移到一个可公开讲解、可本地复现的完整产品中，并重新实现了身份、证据、审批、知识和行动闭环；公司内部实现细节与个人项目代码相互独立。

## 面试官看代码的推荐顺序

1. `knowledge/PRODUCT.md`：业务闭环与边界。
2. `scripts/local_acceptance.py`：端到端证据。
3. `services/media-service/.../workflow`：媒体状态机、outbox 和恢复。
4. `services/agent-service/app/retrievers.py`：授权检索、缓存与融合。
5. `services/agent-service/app/analysis_pipeline.py`：六阶段分析。
6. `services/agent-service/app/publication_service.py`：PRD 审批。
7. `services/agent-service/app/publication_artifacts.py`：不可变版本、知识物化和行动投影。
8. `knowledge/decisions/`：为什么这样选，而不只展示代码结果。

## 三种讲解长度

- 1 分钟：定位、主链路、三个工程关键词、验证数字。
- 5 分钟：架构边界、授权证据链、等待恢复、审批知识闭环。
- 15 分钟：再展开 outbox/幂等、RRF/门控、事务一致性、缓存失效和生产边界。
