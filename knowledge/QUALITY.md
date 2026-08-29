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

2026-08-29 已重新建立完整业务纵向链路的本地证据：

- Agent Service 107/107 用例通过，覆盖六阶段等待/恢复、证据化 PRD、个人二次确认、团队职责分离、不可变版本、知识候选、行动审批、旧图谱迁移、备份恢复往返以及工单/观测/图谱的 tenant/owner 隔离。
- 统一 React Web 完成 `tsc -b` 与 Vite 生产构建。
- Media Service 在声明支持的 JDK 18 下全量 103/103 用例通过，包含 JWT/Workspace、真实注册上传、结构化事件、配额、重试、播放授权和媒体生命周期。
- V6 黄金集的 keyword、embedding、hybrid 三种检索模式均达到 decision 98%、recall@3 97%、fact 97%；最终门禁 p95 分别为 12.2 ms、38.7 ms、41.6 ms，质量门禁通过。
- `python scripts/local_acceptance.py` 在随机 localhost 端口通过全部 14 项检查，覆盖 Workspace 注册、统一 JWT/tenant、视频上传、mock 转写、事务 outbox、Agent 摄取与范围检索、时间戳来源、六阶段等待/恢复、证据化 PRD、个人二次发布确认、不可变版本、知识候选审批、行动项转工单审批、签名播放和 HTTP Range。
- 新增 HTTP JSON 契约和 `compose.local.yml` 已通过机器解析；当前主机未安装 Docker，因此这只是静态配置证据，不等于容器启动证据。

JDK 25 下 Mockito inline/ByteBuddy 不支持该 Java 版本并产生 64 个测试加载错误；这不是产品回归，也不是通过证据。全量质量结论来自受支持 JDK 18 的 103/103 结果。

## 合并门禁

- 相关服务全量测试通过。
- Web 类型检查和构建通过。
- 契约校验、owner/tenant 负向测试通过。
- Agent 行为变化对应评测未退化。
- `python scripts/update_knowledge.py --check` 通过。
- 无法运行的验证必须说明环境原因、影响边界和替代证据。

`.github/workflows/quality.yml` 将门禁拆为 Agent 全量用例 + V6 黄金集、Media JDK 17 全量测试、Web 类型/生产构建和 localhost 平台 smoke。四个 job 独立暴露故障域，避免一个超长脚本掩盖具体失败位置。

## 不允许的质量声明

- mock 中间件通过不等于真实 Redis、MQ、对象存储或模型通过。
- 有 citation 字段不等于引用真实正确。
- UI 隐藏资源不等于完成授权。
- happy path 演示不等于任务具备重试、幂等和恢复能力。
