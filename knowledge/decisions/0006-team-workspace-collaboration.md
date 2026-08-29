# ADR-0006：团队 Workspace 邀请、角色与共享边界

- 状态：已接受
- 日期：2026-08-29

## 背景

个人 Workspace 已提供安全的默认 tenant，但无法覆盖多人共同查看访谈证据、评审 PRD、审批知识与推进工单的业务过程。用户确认把团队协作纳入同一产品，而不是另建项目或依赖服务器、域名和外部身份系统才能验收。

## 决策

- OWNER 创建 team Workspace；创建者获得不可降级的 OWNER 成员关系。
- OWNER 或 ADMIN 可生成一次性、短时有效的邀请码。服务端只保存邀请码 SHA-256，明文仅在创建响应中返回一次。
- 已注册用户接受邀请码后以 MEMBER 加入；同一邀请码只能成功使用一次。
- 只有 OWNER 可把非 OWNER 成员调整为 VIEWER、MEMBER 或 ADMIN；不允许通过角色接口降级或替换 OWNER。
- 用户显式切换活跃 Workspace 后，Media Service 根据服务端成员关系重新签发 JWT；客户端不得自行提交 tenant 或 role。
- personal Workspace 中所有资源保持 owner 私有。team Workspace 中，同 tenant 成员共享读取视频、文档、检索、分析、PRD、知识、图谱和工单；VIEWER 只读，MEMBER、ADMIN、OWNER 可发起写操作。
- 团队 PRD、知识与副作用审批继续执行四眼原则，发起人不能批准自己的动作。
- 成员角色变化对后续签发的 JWT 生效。正式身份提供方接管前，现有短期 JWT 在自然过期前的撤销窗口属于已知本地身份边界，不能宣称为生产级即时撤权。

## 结果

- `tenant_id` 成为真实团队共享边界，`owner_id` 保留创建者归属与审计用途，不再在 team 读取阶段缩小范围。
- Media Service 继续作为账号、成员关系和 JWT 签发来源；Agent Service 只信任共享签名的 active Workspace 声明。
- 本地 H2、SQLite 和 localhost 可以完成双用户邀请、切换、共享读取、角色限制及四眼审批验收。
