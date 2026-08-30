# 数据与安全知识

## 身份模型

- 浏览器只提交受信身份提供方签发的 JWT；两个后端使用相同的 issuer、audience 和签名信任配置。
- `sub` 映射用户身份，`tenant_id` 是强制租户声明，角色/权限来自受信声明或服务端授权表。
- 注册会创建独立 Workspace 和 OWNER 成员关系；`tenant_id` 是 Workspace ID，不等同于 user ID。老账号在首次登录时幂等补建。
- OWNER 可创建 team Workspace；OWNER/ADMIN 签发 15 分钟、一次性的邀请码，服务端只保存 SHA-256。已注册用户消费邀请码后以 MEMBER 加入。
- active Workspace 切换必须由 Media Service 从服务端成员关系重签 JWT；前端不能自报 tenant 或 role。Workspace 角色映射为受信令牌角色：VIEWER→viewer、MEMBER→operator、ADMIN/OWNER→admin。
- 新签发令牌使用身份契约 V2，并携带受信的 `workspace_type=personal|team`。旧 V1 令牌缺失该声明时按 team 处理，不能获得个人 OWNER 自批能力。
- 生产路径禁止使用客户端自报的 `X-Role`、`X-User` 等头部获得权限。
- Agent Service 的兼容身份头仅存在于显式 `development` 模式；`APP_ENV=production` 搭配非 JWT 模式会拒绝启动。
- 服务间调用使用独立的服务身份，同时保留原用户的 tenant/owner 上下文；不能把服务身份当成最终资源所有者。

## 授权规则

- 每一次资源读取、检索、播放、导出和写操作都在服务端校验租户。
- personal Workspace 的资源按 tenant + owner 私有；team Workspace 的资源按 tenant 向成员共享读取，`owner_id` 保留创建者归属与审计信息。
- VIEWER 只读；MEMBER、ADMIN、OWNER 可发起写操作。只有 OWNER 可调整非 OWNER 成员角色，OWNER 不能经普通角色接口被降级或替换。
- 向量检索与图检索必须在查询阶段过滤 tenant/owner，不能检索后再删结果。
- 视频/文档检索、图谱、工单、待审批动作、聊天指标、聊天明细与工具审计都在查询或写入阶段绑定 tenant/owner。旧图谱表会幂等迁移到 `legacy/legacy` 隔离域，不会混入新 Workspace。
- Media Service 是播放授权来源；Agent Service 不持有对象存储凭证。

## 数据最小化与审计

- 跨服务事件不包含存储密钥、永久播放 URL、JWT 或供应商凭证。
- 上传、处理、摄取、分析、PRD 审批、行动执行记录 actor、trace、资源和结果。
- 日志对令牌、凭证、个人敏感字段和大段原始转写做脱敏或截断。
- 模型供应商接收数据前必须经过租户策略检查；相关保留期限和退出策略在生产发布前明确。
- 维护 Skill 的语义索引只扫描版本库内批准的工程文档，不读取客户 SQLite、媒体、`runtime/` 或密钥文件。维护查询缓存只以 query SHA-256 作为 key，不持久化原始问题；生成索引不构成新的业务数据源。
- 分析 evidence snapshot 会在 Agent SQLite 内复制最多 24 个已授权 chunk 的必要事实，以保证等待恢复不漂移；不复制 embedding，也不通过 HTTP 返回快照正文，只返回 revision/hash。读取仍先校验 session 的 tenant/owner/team 语义。当前快照随 session 生命周期保留，正式保留/删除期限仍属于生产数据策略，不能把 hash 当成加密或脱敏。

## 人工审批边界

以下动作默认需要人确认：发布 PRD 为正式版本、把新事实合并进共享知识、创建或更新外部工单、通知外部联系人，以及任何具有不可逆业务影响的工具调用。

PRD 发布已经执行差异化职责分离：个人 Workspace 的 OWNER 必须先申请、再用一次性 token 明确确认；team Workspace 必须由同租户另一位具备写权限的成员批准。状态比较更新、审计事件、不可变 PRD 版本和派生交付物同事务提交；跨租户审批统一返回 404。

分析恢复也使用一次性状态门禁，但不等同于发布审批：`resume_token` 只推进同一业务 checkpoint，数据库按 session/tenant/owner/status/token compare-and-set，竞争失败返回 409；它不会直接发布知识或触发外部写操作。

知识候选不会因 PRD 发布而自动进入正式知识：个人 Workspace 需要 OWNER 单独决定，team Workspace 需要不同写角色成员决定。批准时，候选 CAS、托管知识 document/chunk、图索引和 provenance 同事务提交；失败会整体回滚到 `PENDING`。托管知识不能通过普通文档删除接口移除。替代/撤回必须先创建持久化治理申请；personal OWNER 再次明确决定，team 由不同写成员决定。审批事务软失效旧 document、维护不可变版本链、提升 content revision 并从活跃文档重建图谱，原始证据和历史引用不删除。行动项只会生成受控工具的 pending action，审批成功后才创建工单。团队工单按 tenant 共享读取但保留创建者 `owner_id`；个人工单仍按 owner 私有。

## 待发布决策

本地成员角色变化在下一次重签 JWT 后生效；已签发短期令牌在自然过期前仍可能有效。生产身份提供方、即时撤权机制、默认媒体/转写保留期限和外部模型数据策略必须在生产发布定义前由用户拍板并新增 ADR。
