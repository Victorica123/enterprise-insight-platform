# ADR-0010：批准知识使用版本链完成替代与撤回

- 状态：已接受
- 日期：2026-08-30

## 背景

ADR-0008 已实现知识候选审批、托管文档物化和未来 RAG 再召回，但批准后的错误或过期知识只能保留为永久活跃状态。普通删除又会绕过来源、审批和审计。需要在不改写历史事实、不物理删除证据的前提下，让错误知识停止影响未来回答，并让修订形成可验证的新旧版本链。

## 决策

- 候选审批状态与知识生命周期分离：候选保持 `PENDING/APPROVED/REJECTED`，批准知识另有 `NONE/ACTIVE/REVOKED` 当前状态和不可变版本记录。
- 替代生成新的托管 document/chunk、SHA-256 和 `knowledge_version_id`；旧版本标记 `SUPERSEDED`，双向记录 predecessor/successor。撤回把当前版本标记 `REVOKED`。两者都不物理删除历史 document/chunk。
- 生命周期先创建持久化 `PENDING` 申请。personal Workspace 由 OWNER 通过第二次明确操作决定；team Workspace 必须由不同写成员决定。请求、决定人、原因、时间和结果版本永久保留。
- 决定使用 `BEGIN IMMEDIATE` 和 request/candidate CAS。知识版本、候选当前指针、document 生命周期、content revision、图谱重建和申请终态在同一 SQLite 事务提交；任一步失败整体回滚。
- Retriever 在数据库查询阶段只读取 `documents.lifecycle_status=ACTIVE`，不是检索后再过滤。revision 提升使进程级 Chunk 快照自然失效；图谱按授权 owner scope 从活跃文档原子重建。
- 新产生的聊天日志保存有限的来源快照。回放时保留当时 document/content 引用，同时解析 document 当前状态并显示 `SUPERSEDED/REVOKED` 和替代文档。升级前未保存来源的旧日志不能被逆向补齐。
- Agent Service 继续独占知识生命周期；Media Service 不新增知识事件。当前本地单库事务不冒充跨数据库一致性。

## 结果

错误知识可以从未来 RAG 和图谱中可靠退出，修订知识以新版本继续被授权检索，历史引用仍可审计。代价是增加版本表、治理申请表、历史来源快照和 scope 级图谱重建；当前实现适合本地工程型试点，大规模语料需要增量图谱失效和正式数据库迁移。
