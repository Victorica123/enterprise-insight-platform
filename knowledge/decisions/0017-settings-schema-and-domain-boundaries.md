# ADR-0017：统一配置、编号迁移与可检查的内部边界

- 状态：已接受并实现
- 日期：2026-09-13
- 范围：架构优化计划阶段 1 的向量存储与阶段 3；扩展 ADR-0015

## 决策

`config.py` 是业务环境配置的唯一读取点，以不可变 `Settings` 做类型解析和启动校验，保留原 getter API。环境快照变化会换缓存，兼容测试的环境覆盖；错误只输出参数名与约束，密钥、JWT secret 和数据库凭据不进入 repr。原 provider、模型默认值与出境授权不变。

DDL 从领域 store 收敛到 `app/schema/m001…m007`，`schema_migrations` 记录版本与名称；`database.init_db()` 是唯一协调入口。原 store 初始化函数保留兼容委托，但不重复执行 DDL。SQLite 用进程锁和 `BEGIN IMMEDIATE` 串行升级，失败回滚 schema、数据和 ledger；MySQL 用 advisory lock 串行升级，逐迁移提交，因 DDL 自动提交要求步骤可重试。未知或更高版本 ledger 拒绝启动；后续变化追加迁移，不修改已发布版本。

这改变的是 schema 代码归属：业务事务、知识物化和生命周期仍在各 store，既有 ADR 的授权、审批、原子性与数据所有权不变。旧 `ensure_column`、旧图谱 scope 迁移和已批准知识回填保留。未引入 Alembic；真实 MySQL 升级和回滚演练仍是目标环境验证项，不能以 SQLite 测试代替。

向量以带版本头的小端 float32 blob 读取，同时双写旧 JSON，缺失/损坏 blob 可回退。后台按有界批次补齐旧向量，推理不持有写事务；每次写入校验原内容与活跃状态，只提升实际更新租户的 revision。请求缺少完整语义向量时整批走 hash 降级，避免在请求路径推理文档或混合向量空间。

HTTP 业务依赖统一经 `app.architecture.*`；身份、配置和请求/响应类型是明确基础例外。`graph_algorithms.py` 只遍历调用方已授权的数据，`ticket_domain.py` 保存纯规则；旧模块保留兼容导出。静态边界测试检查路由、环境读取、DDL 和算法依赖。

容器通过 `python -m app.serve` 启动，默认一个 worker；`AGENT_WORKERS`、`AGENT_THREAD_POOL_SIZE`（40）与 `AGENT_SPECIALIST_WORKERS`（4）显式配置。SSE 阻塞阶段与同步 HTTP 共用 anyio 线程池。缓存按数据库与租户 revision 跨进程失效，但每个 worker 有独立模型、缓存和后台维护循环；增加 worker 会增加内存与重复维护开销，不自动等于吞吐提升。

## 验证与剩余范围

回归覆盖旧库数据升级、重复启动、迁移失败回滚、两进程初始化、未知版本拒绝、MySQL 失败释放锁、配置类型/敏感信息、兼容导出及领域边界。SQLite 备份校验和恢复已演练，详见 [QUALITY.md](../QUALITY.md)。

Media 的 Flyway、Java 大服务拆分、任务阶段日志及 Web 路由/查询库仍属于计划阶段 4 的按需项。本次未实施这些项，也没有新的容量或大语料性能结论。
