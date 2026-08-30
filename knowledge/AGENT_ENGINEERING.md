# Agent 工程知识

## 六阶段分析

1. 意图识别：识别会议目标、任务类型和期望交付物。
2. 干系人识别：识别决策者、使用者、执行者、受影响方及立场。
3. 领域深挖：并行提取业务流程、数据、技术约束、规则和术语。
4. 异常与风险：识别矛盾、缺口、依赖、合规与交付风险。
5. 收敛检查：把事实、推断、假设、待确认项分层，判断是否可生成 PRD。
6. PRD 生成：生成带来源、验收口径、风险和未决问题的可评审草案。

阶段是可观测的业务节点，不等同于必须绑定某个 Agent 框架。每一阶段接受结构化状态并产生可校验输出。

当前实现位于独立的 `analysis_pipeline`、`analysis_store`、`publication_service`、`publication_artifacts` 与 `routes/analysis` 模块，没有继续扩张已有的 `agentic_rag.py`。分析会话按 tenant/owner 持久化；事实不足时返回结构化问题和一次性更新的恢复令牌，补充后从收敛点继续并生成带证据与假设标记的 DRAFT PRD。

## 证据策略

- 关键结论必须绑定至少一个可访问证据，或明确标记为假设/建议。
- 视频证据引用稳定资产与片段身份、开始/结束时间、说话人和摘录。
- 发布后的 PRD 以规范 JSON 的 SHA-256 固化为不可变版本；派生知识候选和行动项保留原 requirement 与证据引用，不能脱离来源重新生成事实。
- 批准知识采用规范 Markdown 物化，保存 candidate ID、PRD version、analysis session、内容 SHA-256 与原始证据；后续检索来源明确标记为 `approved_knowledge`。
- 检索结果在进入模型前完成权限过滤；模型不能扩张检索范围。
- 最终答案校验引用存在、归属正确、时间范围有效，并拒绝伪造引用。

## 检索与缓存实现

- hash embedding 是 64 维字符 n-gram 的离线保底；本地 BGE 可用时批量生成 512 维 `embedding_v2`，失败时整体回退，不留下混合维度结果。
- hybrid 先独立执行 keyword 与 embedding，再以 RRF 融合相对排名；证据门控继续使用两路归一化绝对分，避免“只有一个结果所以必然第一”被误判为强证据。
- 可选 cross-encoder 只精排 Top-12，默认关闭；开启前必须用黄金集与延迟预算验证收益。
- chunk 快照 LRU 的 key 包含数据库路径、持久化 content revision 和 tenant/owner/asset scope。写入提升 revision，多进程读不会长期复用旧授权范围或旧内容。
- BGE 向量 LRU 以 model identity + 文本 SHA-256 为 key，最大 512 项；同 batch 去重，缓存只保存向量，不保存原文。该缓存是 embedding 计算复用，不等同于 LLM attention KV cache。
- 两个业务缓存都通过已鉴权的 `/embeddings/status` 暴露进程级 entries、capacity、hits、misses、requests 与 hit rate；统一 Web 监控页展示这些指标。计数不按租户展开、不暴露 key，公开 `/system/status` 不返回缓存流量。
- 工程维护文档另有独立的确定性语义索引，不能被业务检索 API 查询。实现和缓存矩阵见 `TECHNICAL_IMPLEMENTATION.md` 与 ADR-0007。

## 等待与恢复

分析会话需要持久化检查点。遇到真实信息缺口时进入 `WAITING_CONFIRMATION`，记录结构化问题、原因和恢复令牌；用户或授权专家补充后从检查点继续，不从头重跑。

当前状态机已实现 `WAITING_CONFIRMATION → DRAFT_READY → PUBLISH_PENDING → PUBLISHED`。发布逻辑独立放在 `publication_service.py`，交付物投影放在 `publication_artifacts.py`，避免继续膨胀分析路由或既有 `agentic_rag.py`。个人空间要求 OWNER 二次明确确认；团队空间要求不同成员四眼审批。两条路径都使用一次性 token、compare-and-set 状态转换，并在同一事务内写入审计、不可变版本和初始交付物。

## 受控工具

- 工具参数使用 schema 验证，调用前重复鉴权。
- 读工具和写工具分级；有业务副作用的写工具进入审批。
- 重试只用于幂等调用；每次调用保留 trace、输入摘要、批准者和结果。
- PRD 行动项转工单复用 `create_ticket` 受控工具；生成 pending action 不等于工单已创建，只有审批执行后才产生工单。终态会回写为 `TICKET_CREATED/REJECTED/FAILED`，成功时记录真实 `ticket_id`，重复进入请求保持幂等。

## 自进化闭环

- 坏案例：失败答案进入回归数据，记录期望、实际、证据和失败分类。
- 根因：区分摄取、检索、权限、提示、模型、验证和工具错误。
- 改进：优先修复确定性系统问题，再调整提示或模型路由。
- 知识：发布 PRD 生成保留证据的候选；候选经过独立人工决定后才以托管文档进入未来 RAG。候选状态、文档/chunk 与图索引同事务提交，不把 PRD 审批等同于知识审批，也不让 Agent 自动改写规则。
- 门禁：任何影响 Agent 行为的变更必须有对应评测案例，不能仅凭演示判断提升。
