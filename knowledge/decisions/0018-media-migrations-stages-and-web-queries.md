# ADR-0018：媒体迁移、阶段日志与 Web 查询生命周期

- 状态：已接受并实施
- 日期：2026-09-13
- 范围：用户批准继续完成架构优化阶段 4；扩展 ADR-0016/0017

## 决策

Media 的任务配额、租约与完成事务分别进入 `TaskQuotaService`、`TaskLeaseService`、`TaskCompletionService`。`VideoTaskService` 保留兼容入口与接单事务；任务和两个 outbox 的原子性、租户范围与 fencing 保持不变。配置拆为按原 `app.*` 前缀绑定的独立 `@ConfigurationProperties`，`AppProperties` 保留兼容聚合。

Flyway 管理 H2/MySQL 的版本脚本，Hibernate 只做 `validate`。空库自动迁移；没有 Flyway 历史的旧库必须先备份并显式允许 baseline，再通过旧版表、列、主键和唯一约束校验才能登记 V1。禁止 clean、自动 repair 和忽略未来版本。只在隔离副本上演练，现有运行服务与用户数据不在本次改造中直接升级。

新增 `media-task-stages-v1` 查询契约，沿用任务的 JWT/Workspace 授权。阶段仅记录实际执行的取文件、抽音频（仅真实 Whisper 路径）、转写、摘要、复用、提交和投递；不虚构转码。每次执行独立 runId，短事务记录开始、结束与耗时，失败只保存固定错误码。处理任务恢复将旧的处理阶段 RUNNING 标为 ABANDONED，排除独立 outbox 的 DELIVERY；投递进程硬崩溃后遗留的 RUNNING 记录暂不自动关联关闭。查询分页有上限，保留期沿用现有 audit-days。日志不包含正文、文件路径、凭证或租约 token。

Agent HTTP 每次只发送一次，服务端 outbox 继续负责持久化退避和最大重试次数。熔断只在连续暂时性故障时暂停出站，半开只允许一个探测；熔断跳过不消耗投递次数。按需领取待发送事件，避免整批事件在等待网络时耗尽租约。

Web 使用 React Router 管理可回退的页面地址，TanStack Query 管理服务器数据、去重、失效与有界重试；查询把 AbortSignal 传到 HTTP。查询缓存按身份、Workspace 与角色隔离，在身份边界切换时取消并清空。页面状态下沉到 feature/controller，QA 继续复用现有会话与 SSE 实现。

真实 MySQL 验收补充三处兼容修复：旧库校验兼容 Connector/J 的 `ENUM` 元数据；Agent 新增不可变编号迁移 `m008_mysql_text_fields`，把七个证据/版本/生命周期长文本列升级为 LONGTEXT（SQLite no-op），已有 1–7 迁移不改写；监控聚合 SQL 的 `key` 别名显式引用。前端禁用 viewer 的媒体、文档和分析写入口，仍由后端 JWT 与四眼规则实施最终授权。

## 验证与边界

Media 150/150、Agent 244/244、Web 21/21；H2/SQLite 与真实 MySQL/Redis/RocketMQ/MinIO 均完成 42/42 纵向验收。真实 MySQL 覆盖旧库/新库、重启、Agent 并发初始化、未来版本拒绝、长文本保存及两库备份恢复；Agent 断连恢复和有限 k6 冒烟通过。浏览器验证路由、连续追问、停止、迟到响应隔离、跨标签页角色更新和 viewer 只读。日志、口径和边界见 `knowledge/QUALITY.md` 最新条目；本轮使用 HS256 与 mock/local AI，未验证 Keycloak/RS256、外部 AI、长时间容量或多实例灾备。
