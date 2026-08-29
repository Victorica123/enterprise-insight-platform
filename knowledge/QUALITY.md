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

- Agent Service 113/113 用例通过，覆盖 team Workspace 下文档、视频证据、分析、图谱和工单的 tenant 共享，personal owner 隔离，VIEWER 只读、受信 JWT 检索范围，以及真实 embedding 的批内去重与摘要 key LRU 复用；原有六阶段、发布治理、备份恢复与 tenant/owner 负向用例保持通过。
- 统一 React Web 完成 `tsc -b` 与 Vite 生产构建。
- Media Service 在声明支持的 JDK 18 下全量 108/108 用例通过，新增覆盖团队创建、一次性邀请、角色调整、active Workspace 重签、跨成员媒体读取、个人隔离和 VIEWER 写入拒绝；原有结构化事件、配额、重试、播放授权和媒体生命周期保持通过。
- V6 黄金集的 keyword、embedding、hybrid 三种检索模式均达到 decision 98%、recall@3 97%、fact 97%；Embedding 缓存改动后的门禁 p95 分别为 18.9 ms、31.6 ms、19.4 ms，均低于 500 ms 阈值，质量门禁通过。该单机结果证明无回归，不直接外推生产吞吐。
- `python scripts/local_acceptance.py` 在随机 localhost 端口通过全部 21 项检查：除原个人闭环外，新增双用户团队创建/邀请/切换、跨成员媒体与 Agent 检索、personal 隔离、团队四眼发布、知识/工单交付和 VIEWER 只读；全程仅使用本机临时 H2/SQLite/local 文件和 mock/local AI。
- 真实浏览器在 1280×720 视口完成登录、团队创建、邀请生成和 Workspace 切换；测试捕获到 sticky header 的 containing block 导致 fixed 弹窗越界，改为通过 Portal 挂载到 `document.body` 后，弹窗完整位于视口内且切换成功。
- 维护知识索引 3/3 单元测试通过，覆盖未变化 chunk 向量复用、语义路由、corpus revision 查询缓存失效和 `docs/archive` 排除；当前索引为 30 个批准来源、138 个有效 chunk。仓库版与安装版维护 Skill 均通过 Skill Creator quick validation，真实查询已验证 miss→hit。
- 新增 HTTP JSON 契约和 `compose.local.yml` 已通过机器解析；当前主机未安装 Docker，因此这只是静态配置证据，不等于容器启动证据。

JDK 25 下 Mockito inline/ByteBuddy 不支持该 Java 版本并产生测试加载错误；这不是产品回归，也不是通过证据。全量质量结论来自受支持 JDK 18 的 108/108 结果。

## 合并门禁

- 相关服务全量测试通过。
- Web 类型检查和构建通过。
- 契约校验、owner/tenant 负向测试通过。
- Agent 行为变化对应评测未退化。
- `python scripts/update_knowledge.py --check` 通过。
- 无法运行的验证必须说明环境原因、影响边界和替代证据。

`.github/workflows/quality.yml` 将门禁拆为 Agent 全量用例 + V6 黄金集 + 维护索引单测与知识漂移、Media JDK 17 全量测试、Web 类型/生产构建和 localhost 平台 smoke。四个 job 独立暴露故障域，避免一个超长脚本掩盖具体失败位置。

## 不允许的质量声明

- mock 中间件通过不等于真实 Redis、MQ、对象存储或模型通过。
- 有 citation 字段不等于引用真实正确。
- UI 隐藏资源不等于完成授权。
- happy path 演示不等于任务具备重试、幂等和恢复能力。
