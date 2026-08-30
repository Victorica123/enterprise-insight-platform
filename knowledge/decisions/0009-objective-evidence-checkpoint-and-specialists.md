# ADR-0009：目标证据快照、阶段检查点与有界领域 specialist

- 状态：已接受
- 日期：2026-08-30

## 背景

六阶段分析已经能持久化 session、等待人工补充并生成带证据的 PRD，但初版确认路径会重新读取当前授权材料、重算全部阶段，并用普通 upsert 保存。由此存在三类可验证缺口：同一 `resume_token` 可能被并发消费两次；等待期间知识库变化会让早期结论漂移；目标只用于标题而未参与分析证据排序。领域阶段也是单个同步规则函数，无法展示有界并行、失败隔离和冲突升级。

## 决策

- 创建分析会话时先在 tenant/owner/asset 授权范围内使用 hybrid 检索按 objective 排序，最多选择 24 个正分 chunk。
- 在持久化前验证 content revision 稳定，把排名、分数、匹配 query 与必要 chunk 事实序列化为 canonical JSON；保存 revision 和 SHA-256。embedding 向量不复制进快照。
- 快照只供该 session 内部恢复使用；HTTP 仅返回 `evidence_revision`、`evidence_snapshot_sha256`、`retrieval_mode` 与 `checkpoint_version`，不扩大原文暴露。
- 确认恢复使用冻结快照并保留阶段 1–4，只重算收敛检查和 PRD。它是持久化业务阶段检查点，不声称恢复 Python 执行栈，也不引入 AppServer、WebSocket 或常驻执行上下文。
- `resume_token` 通过 `session_id + tenant_id + owner_id + WAITING_CONFIRMATION + resume_token` 的 SQLite compare-and-set 原子消费；成功后检查点版本递增，失败返回 409。
- 领域阶段固定调度业务、数据与安全、技术与集成、规则与合规四个本地确定性 specialist，线程池上限为 4。结果按声明顺序合并，不按完成顺序合并；单个失败转为人工复核问题，显式冲突转为 `domain_conflict` 问题。
- specialist 是有界领域执行器，不冒充独立 LLM Agent。Phase 1 不依赖外部模型、服务器或域名；模型化专家、实时传输和知识撤回/废弃保持后续独立决策。
- 新增 PRD 专项黄金集，覆盖目标排序、授权隔离、缺口判断、冲突升级、检查点稳定、视频时间证据、引用支持和可测试验收；CI 中与既有 V6 RAG 门禁并行执行。

## 结果

相同会话在等待期间获得可重放、可核验的证据边界，并发确认只有一个请求能推进状态。目标开始实际影响证据次序，阶段恢复与领域并行都有代码和回归证据。代价是 session 表增加快照存储，规则 specialist 的语义覆盖仍受关键词限制；真实业务分布、LLM 专家收益和生产级数据库迁移必须另行评估，不能由 12 例本地黄金集外推。
