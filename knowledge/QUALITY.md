# 质量知识

## 分层验证

- 单元：纯领域逻辑、状态机、鉴权、切分、引用验证、幂等。
- 服务：API、数据库迁移、任务重试、错误映射和可观测性。
- 契约：事件 schema、共享 JWT 声明、生产者与消费者兼容性。
- Agent 评测：检索命中、引用正确性、越权拒绝、冲突识别、PRD 完整性。
- 平台 smoke：真实登录后上传视频，等待转写，提问并点击时间戳回放。

## 当前已知基线

- Agent Service 在整合前的回归基线为 87 个 pytest 用例通过；首批契约、幂等摄取、检索隔离、JWT 与时间戳引用加入后为 98 个用例通过。
- React 应用在整合前可完成 TypeScript/Vite 生产构建。
- Media Service 声明支持 JDK 17/18；JDK 25 下 Mockito inline/ByteBuddy 失败属于不支持工具链，不能作为服务回归结论，也不能当作通过。

2026-08-29 已重新建立首条纵向链路的本地证据：

- Agent Service 102/102 用例通过，新增六阶段等待/恢复、证据化 PRD、个人二次确认、团队职责分离与分析会话租户隔离回归。
- 统一 React Web 完成 `tsc -b` 与 Vite 生产构建。
- Media Service 生产与测试源码完成 Maven 编译；JWT/Workspace、真实注册上传、结构化事件契约定向测试通过。
- `python scripts/local_acceptance.py` 在随机 localhost 端口通过，覆盖 Workspace 注册、统一 JWT/tenant、视频上传、mock 转写、事务 outbox、Agent 摄取与范围检索、时间戳来源、六阶段等待/恢复、证据化 PRD、个人二次发布确认、审计查询、签名播放和 HTTP Range。

当前 Media Service 的结构化转写新增测试在本机 JDK 25 下可定向运行通过，生产与测试源码均已完成 Maven 编译；全量 Media 回归仍需按声明的 JDK 17/18 执行，不能用当前 JDK 25 的 Mockito/ByteBuddy 兼容性结果替代。

## 合并门禁

- 相关服务全量测试通过。
- Web 类型检查和构建通过。
- 契约校验、owner/tenant 负向测试通过。
- Agent 行为变化对应评测未退化。
- `python scripts/update_knowledge.py --check` 通过。
- 无法运行的验证必须说明环境原因、影响边界和替代证据。

`.github/workflows/quality.yml` 将门禁拆为 Agent 102 用例 + V6 黄金集、Media JDK 17 全量测试、Web 类型/生产构建和 localhost 平台 smoke。四个 job 独立暴露故障域，避免一个超长脚本掩盖具体失败位置。

## 不允许的质量声明

- mock 中间件通过不等于真实 Redis、MQ、对象存储或模型通过。
- 有 citation 字段不等于引用真实正确。
- UI 隐藏资源不等于完成授权。
- happy path 演示不等于任务具备重试、幂等和恢复能力。
