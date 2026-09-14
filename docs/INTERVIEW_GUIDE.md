# Enterprise Insight Platform 面试讲解与技术答辩

本文统一维护口述、框架取舍、技术追问、代码核对和个人贡献边界；现场操作与计时练习见 [演示脚本](DEMO_SCRIPT.md)。2026-09-14 按应用代码基线 `c779ce6` 核对，文档整理不代表应用能力升级。

原面试演练手册的口述与故事、压力评审的追问与经历边界已合入本文；演示和练习步骤合入演示脚本。旧稿保留在 Git 历史，不再并行维护重复答案。数字与环境查 [QUALITY](../knowledge/QUALITY.md)，实现语义查 [Agent 工程知识](../knowledge/AGENT_ENGINEERING.md)。

## 一分钟项目介绍

> 我做的是面向客户访谈和需求评审的企业洞察平台，把视频和文档转成可追溯证据、PRD、受治理知识和工单。Spring Media Service 负责身份与媒体，FastAPI Agent Service 负责知识与分析，React 提供统一工作台。分析先在授权范围按目标检索并冻结证据，再由四个规则 specialist 并行提取事实；缺信息时等待人工确认，恢复时保留已完成阶段。PRD 发布、知识沉淀和工单执行分别审批。我重点讲解授权检索、跨服务幂等、业务检查点和副作用治理。当前本机验收证明工程闭环，六阶段仍是规则基线，真实模型效果和生产容量需要独立证据。

20 秒版：平台把会议材料连接到证据、需求、知识与行动；核心是让结论可追溯、写操作受控，问答侧可以接 LLM，交付分析保持可复现的规则基线。“我做了什么”须按本人实际参与调整，不能把迁移来源、团队经历或 AI 辅助产出全部说成从零手写。

<a id="framework-choice"></a>
## 为什么自研编排，而不是主流框架

### 面试可直接回答的版本

> 我没有从零开发通用 Agent 框架，只实现了当前业务需要的一层编排。Web、类型校验和模型调用仍使用 FastAPI、Pydantic 和 OpenAI-compatible SDK。当前流程比较固定，关键约束是授权证据、人工确认、审批事务和幂等；我用显式执行计划、状态对象与执行器把这些约束接起来，能在不调用外部模型时验证业务状态。优势是项目内的数据流和业务约束容易检查，依赖面比较小。代价是截止时间、队列容量、取消和恢复等运行时能力需要自己维护，目前确实还有缺口。如果后续出现大量动态分支、长期任务和多个模型 Agent，我会评估 LangGraph 等成熟运行时，并保留现有鉴权、事务和评测边界。

这是基于当前代码的选型解释，不是已经做过框架性能对照实验的结论。

### 公平比较替代方案

| 方案 | 可以提供的能力 | 本项目仍需负责的工作 |
| --- | --- | --- |
| LangChain | 模型、工具、检索等组件与集成；其 Agent 构建在 LangGraph 之上 | tenant/owner 授权、证据生命周期、审批规则与数据库副作用 |
| LangGraph | 显式状态图、持久化执行、检查点与人工介入等运行时能力 | 哪些状态可恢复、外部写入如何幂等、审批与业务事务如何一致 |
| 当前自研编排 | 固定流程的执行计划、模式分发、状态与业务检查点 | 通用调度由项目承担，没有继承成熟框架的完整运行时保障 |

参考：[LangChain 概览](https://docs.langchain.com/oss/python/langchain/overview)、[LangGraph 概览](https://docs.langchain.com/oss/python/langgraph/overview)。框架可以和业务治理代码结合，不能以“框架不支持检查点、人工确认或企业权限”为由排除框架。

### 优势、代价与迁移条件

| 当前取舍 | 仓库证据 | 代价 |
| --- | --- | --- |
| 执行路径明确 | `PreparationChain → ExecutionPlan → ExecutorRegistry`；冻结计划后分发到唯一模式执行器 | 动态分支复杂后，手工调度成本会上升 |
| 业务状态可复现 | evidence revision/hash；确认保留阶段 1–4；CAS 消费恢复令牌 | 不是模型调用或 Python 栈中途恢复 |
| 测试输入可控制 | 可注入执行器、规则基线与冻结场景，无外部模型也能回归 | 可测试不等于模型质量已达标 |
| 依赖与适配面较小 | 直接使用 Pydantic、标准库并发与 SDK，没有 Agent 框架依赖 | 自己维护超时、取消、追踪和队列并不免费 |

没有同条件基准，不能声称自研更快、更省 token 或更可靠。权限、证据和审批是应用要求，不是自研方案独有优势。

当动态图/回路、跨请求长时任务、多模型协作、连接器复用或调试回放需求持续增长时，用同一业务切片做框架原型，对比维护工作量、失败恢复、最终质量、延迟和成本。通过现有黄金集、授权与副作用回归后再决定替换。`Executor` 接口可作为适配入口，领域存储、审批和检索授权继续保留；不需要为了框架名称重写整个系统，也不能因为已经自研就拒绝成熟运行时。

<a id="agent-boundaries"></a>
## Agent 是什么，如何通信

| 路径 | 当前实现 | 边界 |
| --- | --- | --- |
| 问答 | Router、Planner、工具选择和生成可调用 LLM；失败或未配置时有规则/模板路径 | 不是每次请求都调用所有模型角色 |
| 六阶段分析 | 意图、相关方、领域、风险、收敛、PRD；四类 specialist 做关键词/规则提取 | specialist 没有专家 Prompt 或独立模型调用 |
| 引用 Reviewer | 标准引用与部分数字锚点的轻量规则 | 不是完整语义事实审查模型 |

问答通过 `ExecutionPlan`、`AgenticRagState` 传递问题、查询、证据、工具结果和 trace。领域分析由中心编排器分发同一冻结证据，四个 specialist 返回 `DomainSpecialistResult(findings, evidence, error)`，按业务、数据安全、技术集成、规则合规的固定顺序合并。

这是同进程函数调用与 Future 汇总，没有 Agent 间网络协议、自由对话或分布式消息总线。固定顺序不代表完整语义冲突消解；当前主要识别材料中明确出现的冲突表述。

Media 到 Agent 是另一层通信：业务事务写 outbox，领取 claim/lease 后通过 HTTP 发送版本化事件，携带 scope、trace 与幂等标识。它不是 specialist 的通信方式，也不能把媒体任务队列等同于跨服务证据投递。

代码：[编排器](../services/agent-service/app/architecture/orchestration.py)、[问答状态](../services/agent-service/app/agentic_rag.py)、[领域分析](../services/agent-service/app/analysis_pipeline.py)、[服务边界](../knowledge/ARCHITECTURE.md)。

<a id="retrieval"></a>
## 如何考虑召回率与检索质量

先对 tenant、personal owner 和 asset 做授权，再执行通道召回、质量过滤、融合、相邻块扩展、可选精排和证据预算。问答支持查询改写与最多两轮检索。

- 关键词提供精确匹配，真实 BGE 可提供语义向量；真实语义通道可用时，关键词与语义检索名次通过 RRF 融合。
- hash embedding 是离线保底，采用 `keyword_then_hash`，不把哈希碰撞当独立语义投票。
- 同文档、同章节的授权相邻块补充上下文；主题过滤仍生效，视频保留独立时间定位。
- 可选 cross-encoder 只精排 Top-12，默认关闭；故障时保留精排前顺序。
- `selection_rank` 与相关性 `score` 分开，最终 Top-K、预算与分析快照不能覆盖融合/精排名次。

调大 Top-K、降低阈值可能减少遗漏，也会增加噪声、成本和错误依据。分别定位未摄取、切分损失、检索未命中、排序被挤出、预算裁掉与生成遗漏，不能只靠放松门槛改善数字。

真实修复案例：回答层曾重新按分数排序，覆盖 RRF/reranker 结果。回归现在验证标准问答、Agentic 问答和分析快照使用最终名次；见 [参考站复核](NEXUS_REFERENCE_AUDIT.md) 与 [检索回归](../services/agent-service/tests/test_retrieval_pipeline.py)。

<a id="fault-isolation"></a>
## Agent 报错、卡死或进程退出怎么办

| 故障 | 当前行为 | 实现边界 |
| --- | --- | --- |
| LLM 请求/解析失败或预算耗尽 | 路由/规划/工具选择退回规则，生成可退回证据模板；SDK 配置超时与有限重试 | 次数限制不等于整个请求有统一截止时间 |
| 检索通道失败、超时或满员 | 默认 2 秒截止，各通道默认 4 个在途槽位；用健康通道，证据不足拒答 | 已运行原生推理不能靠取消 Future 强杀，仍占槽至退出 |
| reranker 不可用 | 默认 3 秒截止，保留此前排序，trace 记录降级 | 不能说精排一定成功 |
| specialist 抛异常 | 记录 error，保留其他维度，提出人工确认问题 `specialist_review` | 回归覆盖异常，不覆盖永久挂起 |
| specialist 永久挂起 | `as_completed(futures)` 没有 timeout，分析请求可能一直等待 | 4-worker 限线程数，共享提交队列没有容量限制 |
| 整个 Agent 进程退出 | 重启后可读取已持久化业务状态 | 没有独立 specialist 进程隔离，也不能从模型调用中途续跑 |

问答 SSE 有取消传播、有界事件队列和上游流总时限，不代表六阶段 specialist 具备相同保障。迟到检索结果不会回写响应，不能推断所有任务都有统一 fencing。

后续补强方案，**本次仅记录、尚未实施**：给 specialist 汇总与请求设截止时间，限制在途/排队任务，区分必需和可选分支，拒绝迟到写入。强制终止要求独立进程或 worker；长任务再配任务 ID、持久化状态、租约和幂等重试。可选分支返回部分结果；缺关键证据或审批则快速拒答/人工确认，不能带缺口自动发布。

代码：[通道隔离](../services/agent-service/app/retrieval_execution.py)、[specialist 等待](../services/agent-service/app/analysis_pipeline.py)、[LLM 客户端](../services/agent-service/app/llm_client.py)。

<a id="evaluation"></a>
## 如何评估效果，如何解释数字

2026-09-13 保存的 V6 结果为 45 题，其中 40 题应回答、5 题应拒答；hybrid 决策正确 44/45，Top-3 来源命中与事实子串命中均为 39/40。原始环境、日志、PRD 12 例与会话 14 场景结果查 [质量记录](../knowledge/QUALITY.md)。这些是历史验证，2026-09-14 文档整理没有重新验证真实模型效果。

| 指标 | 当前计算方式 | 面试解释 |
| --- | --- | --- |
| `decision_accuracy` | 证据门控是否放行，与标注应答/拒答比较 | 不代表答案内容全部正确 |
| `recall3` | 前三条返回来源命中任一目标文档的问题比例 | 更准确称 Hit@3 / Top-3 来源命中率 |
| `fact_coverage` | 已回答且含任一预期事实子串的问题比例 | 不是全部事实覆盖率或逐陈述真实性 |
| PRD 场景 | 缺口、冲突、目标证据、支持关系、验收与检查点等断言 | 规则回归，不能外推真实 PRD 接受率 |
| 会话与治理场景 | 指代、换题、证据更新、隔离、知识版本、审批与回滚 | 功能正确性，不能替代开放域语义质量 |

严格 Recall@K = 检出的相关证据数 / 标注的全部相关证据数；Precision@K = 返回结果中的相关数 / 返回结果数。若需要三份证据却只命中一份，Hit@3 可为 1，而完整召回仅为 1/3。当前指标名保留兼容，本次没有更改脚本或历史值。旧版本曾把最多四条来源算入 `recall3`，不能把历史栏当作严格 Top-3 横向比较。

当前评测使用 hash/local、关闭 LLM Router；黄金集与规则共同维护，缺少独立真实分布 holdout。测试数量、约 98% 的展示数字和本地毫秒级耗时不能包装成真实模型准确率或线上性能。

下一步先冻结脱敏真实留出集和标注标准，再分层观察：

1. 节点：路由正确、计划覆盖、工具/参数正确、失败降级。
2. 检索与生成：严格召回/精度、逐陈述支持率、遗漏/矛盾、正确与错误拒答。
3. 完整任务：PRD 人工修改率、接受率、审批与工具任务完成率。
4. 运维与成本：端到端 P95、超时率、token、费用、人工接管率。

采用第二人独立评审；LLM judge 只辅助并用人工样本校准。对模型/Prompt/检索变更用同一留出集对照并做组件消融。线上反馈需经标注形成坏案例，不能直接当真值。

代码：[V6 judge](../quality/agent-evals/evaluate_v6.py)、[PRD 评测](../quality/agent-evals/evaluate_prd.py)、[会话评测](../quality/agent-evals/evaluate_conversation.py)、[指标窗口回归](../services/agent-service/tests/test_evaluation_contracts.py)。

<a id="hallucination-control"></a>
## 如何预防与处理幻觉

已实现：授权后检索、主题与证据门控、资料不足澄清/拒答、限定入模上下文、每轮重新读取活跃证据、历史回答不充当新事实、结构化工具参数校验、写操作审批。结构合法、来源有权限和答案事实正确是不同检查。

当前 `review_citations` 检查是否存在至少一个合法样式的来源标记，以及部分数字/日期能否在来源中找到锚点；缺引用时追加来源列表。可疑数字只触发人工核对警告，状态仍可能是 `passed`，不是自动阻断，也未逐条验证全部引用或语义支持。

例如来源说“负责人是张三”，答案写“负责人是李四 [来源 1]”，规则可能放过。出现来源里的数字也不能证明主体、因果或单位正确。六阶段没有生成模型，规则提取仍可能出错，照样需要评测与人工复核。

后续严格处理方案，**尚未实施**：拆分事实陈述，逐条绑定来源片段；验证所有引用 ID、数字、实体和矛盾，再做语义支持判断。无支持内容删除、明确降为假设或有限次重新生成；仍失败就拒答/人工接管。不能无限重试到某个 Reviewer 给出通过，也不能把同一模型自审作为唯一依据。SSE delta 是待审内容，done 才是最终审核结果，但审核能力仍受上述限制。

资料本身错误时，已有治理可以处理：申请替代/撤回，经审批修改版本状态，更新 content revision 与图谱，未来检索只用 ACTIVE 文档；历史引用保留并显示失效状态。坏案例按摄取、检索、生成或校验根因归档，避免修错层。

代码：[引用审核](../services/agent-service/app/citation_review.py)、[证据门控](../services/agent-service/app/rag.py)、[知识生命周期](../services/agent-service/app/knowledge_lifecycle_store.py)。

<a id="governance"></a>
## 其他高频追问：身份、恢复、知识和上线

| 问题 | 当前答案与边界 |
| --- | --- |
| 为什么两个后端 | Media 管身份和媒体长任务，Agent 管知识和分析；状态机与数据所有权不同，统一前端/契约，不共享业务表；代价是投递与跨服务授权更复杂。 |
| 为什么不用向量库 | 保留可复现本地基线，按语料量、P95、内存和多实例需求迁移；保留授权 pre-filter 与回归，没有规模对照就不宣称当前性能更优。 |
| 如何防 RAG 越权 | tenant/owner/asset 下推候选查询和缓存 key；team 按 tenant 共享，personal 按 tenant+owner 私有；team owner 保留审计归属。 |
| 缓存如何失效 | Chunk key 含数据库、revision 和 scope，写入提升 revision；BGE key 含模型身份与内容摘要。缓存不是模型 attention KV cache。 |
| 角色变更即时生效吗 | 前端按身份/Workspace/角色重建查询上下文；已有 JWT 的服务端撤权要按部署机制核对，不能凭 UI 清缓存宣称即时撤权。 |
| 视频来源有多可信 | 保存 asset/segment/时间范围，播放时申请 Media 授权；保证定位和权限，不证明转写无误或答案逐句被支持。 |
| checkpoint 恢复哪层 | 保存 session、阶段、确认与证据快照，保留阶段 1–4，只重算收敛/PRD；CAS 消费 token，竞争回归一个 200、一个 409；新资料需新建分析。 |
| SSE 还是 WebSocket | 问答已有 SSE，媒体轮询，分析确认走 HTTP；没有 AppServer/WebSocket continuation，也不自动重放客户端漏收的 done。 |
| 为什么独立审批 | PRD 发布与知识影响未来检索是不同决定；personal OWNER 二次确认，team 不同成员四眼；行动项再进入受控工具审批。 |
| 知识批准只是改状态吗 | 候选、托管 document/chunk、版本/证据、revision 与图谱事务物化，失败回滚，未来 RAG 可检索；替代/撤回保留历史。 |
| outbox 能保证什么 | 业务与 outbox 同事务；claim/lease、过期接管、旧 worker fencing、退避与 DEAD；Agent 做事件和业务版本双幂等；仍是 at-least-once。 |
| 能大规模上线吗 | 有本机中间件、迁移/还原证据；目标 IdP/撤权、外部模型、长时容量、多实例、灾备与聚合告警仍需验收；没有客户 ROI 或生产 SLA 证据。 |

细节分别由 [数据与安全](../knowledge/DATA_AND_SECURITY.md)、[Agent 工程](../knowledge/AGENT_ENGINEERING.md)、[运维](../knowledge/OPERATIONS.md) 和 [质量](../knowledge/QUALITY.md) 维护。

<a id="cross-examination"></a>
## 连续追问练习

先给结论，再指出代码、证据、取舍和缺口，不靠罗列框架名称回避问题。

| 主题 | 让同伴继续追问 |
| --- | --- |
| 选型 | LangGraph 已有 checkpoint 和人工介入，为什么还自研？省哪些适配、增哪些维护？有性能对照吗？何时换？ |
| Agent 真实性 | 指出实际模型调用；四个 specialist 为什么是规则？前 8 个 chunk 投影 PRD 有何语义局限？ |
| 故障 | 异常与卡死有何区别？4 worker 是否限制队列？Future.cancel 能否停掉正在运行的推理？进程退出怎么办？ |
| 检索/评测 | 证据召回后在哪一步丢失？Hit@3 与 Recall@3 有何区别？任一事实命中能证明整段正确吗？ |
| 幻觉 | 合法引用但主体错了怎么办？警告是否阻断？已显示的待审 SSE 内容怎么解释？ |
| 恢复 | 保存哪些数据？等待期间资料更新怎么办？双请求消费同一 token 如何只成功一次？ |
| 治理 | PRD 为什么不直接变知识？撤回如何影响缓存、图谱与旧聊天？写工具何时执行？ |
| 一致性 | Media 成功但 Agent 不可用怎么办？谁领取 outbox？同版本不同内容为何拒绝？重复和乱序如何判断？ |
| 生产/价值 | 100 个团队的瓶颈怎么测？哪些中间件实测过？PRD 修改率、ROI 与 SLO 证据在哪里？ |
| 个人贡献 | 哪些来自迁移、哪些新增、哪些由 AI 辅助？随机打开状态转换，能否独立解释并写回归？ |

<a id="stories"></a>
## 三个可复述的工程故事

**业务闭环。** 原能力分别提供视频处理和问答；整合先固定 Media/Agent 数据所有权与可信身份，再串起时间证据、目标检索、阶段确认、PRD、知识和工单。双用户验收证明状态与权限；业务价值仍待真实用户验证，可测 PRD 周期、人工修改率和行动关闭率。

**并发迁移缺陷。** 历史浏览器并发请求触发 SQLite `duplicate column name: owner_id`，根因是先检查后 ALTER 的竞态。当时仅在重新确认列已存在时接受并发完成，没有吞掉所有数据库异常；后续收敛为编号迁移、ledger 和启动锁。批准/物化用短事务与 CAS，模型/网络不放进锁内。原复测见 QUALITY 历史，不把当时测试数当最新值。

**两服务与授权缓存取舍。** 保留不同生命周期的服务，承担 HTTP outbox 和幂等成本；检索与缓存同时带 scope 和 revision。对比合并服务、全库检索后过滤、立即引入向量库等方案，说明数据归属、安全和运维成本；规模优化由代表性负载触发，不虚构缓存提速倍数。

<a id="contribution"></a>
## 简历、实习与 AI 辅助的边界

原压力评审参照过用户提供的 2026-08-25 版简历；仓库只能证明自身实现，不能验证实习贡献、业务量或公司内部系统。

| 容易混淆的经历/术语 | 本项目事实 |
| --- | --- |
| PD-Agent 六阶段与专家 | 可说明方法启发；四个专家是规则执行器，未接企业 IM 专家路由 |
| AppServer、WebSocket、continuation | 未引入这些运行时；HTTP 业务恢复与问答 SSE 各自存在 |
| Wiki 对照、Bad Case 自动升级 Skill | 业务知识独立审批物化；Skill 索引与客户知识隔离，无自动发布规则或 Wiki diff |
| 金融规则、列级权限、数仓入仓 | 资源/租户授权与事件摄取，不能移植金融、列级 SQL 或 Databus2Hive 能力 |
| Redis 预扣减、RocketMQ 一致性 | Media 可用分片/任务队列；跨服务证据是 HTTP outbox，业务语义不同 |
| 实习吞吐、告警、ROI 和 SLA | 不得移植数字；项目依据是仓库测试、故障注入和本机记录 |
| AI 辅助与迁移代码 | 如实区分来源、生成辅助、本人决策与验证，不声称全部从零手写 |

只有符合本人实际经历时，才能使用“方法迁移、独立实现”的表述。展示本仓库接口、合成数据与回归证据，不展示公司内部 Prompt、协议或数据。

<a id="code-walk"></a>
## 十分钟代码核对路线

| 入口 | 要能解释的内容 |
| --- | --- |
| [编排器](../services/agent-service/app/architecture/orchestration.py) / [依赖](../services/agent-service/requirements.txt) | 框架边界、模式分发、调用预算 |
| [分析证据](../services/agent-service/app/analysis_evidence.py) / [流水线](../services/agent-service/app/analysis_pipeline.py) | 目标检索、冻结范围、规则 specialist、无超时等待、PRD 投影局限 |
| [分析存储](../services/agent-service/app/analysis_store.py) | CAS、checkpoint version、证据 hash；同库 hash 检测漂移，不防管理员同时改正文与 hash |
| [检索执行](../services/agent-service/app/retrieval_execution.py) / [引用审核](../services/agent-service/app/citation_review.py) | 截止与槽位的保障；告警与语义校验的差别 |
| [发布](../services/agent-service/app/publication_service.py) / [知识事务](../services/agent-service/app/knowledge_lifecycle_store.py) | personal/team 审批、物化、版本与回滚 |
| [outbox](../services/media-service/src/main/java/com/example/videoplatform/integration/AgentOutboxDispatcher.java) | claim、lease、HTTP 失败与重投 |
| [V6](../quality/agent-evals/evaluate_v6.py) / [纵向验收](../scripts/local_acceptance.py) | 指标分母、judge、mock 与真实环境边界 |

优先补强 specialist 截止/容量、严格引用与事实审核、真实模型独立留出集。本轮仅记录待办，没有实现这些功能，也没有更换模型、框架或扩大生产发布范围。
