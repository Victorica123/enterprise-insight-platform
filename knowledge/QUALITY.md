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

2026-08-30 完成业务缓存可观测性增量验证：

- Agent Service 全量 116/116 通过；新增用例覆盖 hit rate 计算、零请求语义、tenant/owner/asset 授权范围分键，以及已鉴权 `/embeddings/status` 与机器 JSON 契约的一致性。公开 `/system/status` 的响应负向断言确认不包含缓存流量。
- `contracts/http/cache-observability-v1.schema.json` 通过机器解析；Agent 聚焦契约/缓存测试 19/19 通过。
- 统一 Web 再次完成 `tsc -b` 与 Vite 生产构建，缓存监控的前后端类型闭环通过。
- V6 黄金集保持 keyword、embedding、hybrid 的 decision 98%、recall@3 97%、fact 97%，本轮 p95 分别为 13.5 ms、28.5 ms、18.2 ms，质量门禁通过。该结果用于证明指标采集未改变检索行为，不代表生产吞吐。
- localhost-only 纵向验收扩展为 23 项并全部通过；新增验证匿名缓存状态被拒绝、公开系统状态不暴露缓存流量，以及真实检索后授权 Chunk 缓存计数可见。仍只使用随机本机端口、临时 H2/SQLite/local 文件与 mock/local AI。
- 维护知识索引单元测试 3/3 通过，覆盖语义路由、增量向量复用、revision 缓存失效和归档排除。

2026-08-30 完成面试收尾与批准知识闭环验证：

- Agent Service 全量 119/119 通过；新增覆盖批准知识物化、candidate/PRD/hash provenance、托管知识删除保护、图索引失败时整体回滚，以及浏览器并发加载触发的 SQLite 兼容列迁移竞态回归。
- `contracts/http/approved-knowledge-v1.schema.json`、扩展后的 publication deliverables 与 evidence source 契约通过解析和契约测试。
- localhost-only 纵向验收扩展为 25 项并全部通过；新增验证批准候选生成受治理知识、后续问答命中 `origin_type=approved_knowledge`，且 candidate ID 与内容哈希一致。
- Media Service 在 JDK 18 下保持 108/108；统一 Web 再次完成 TypeScript/Vite 生产构建。
- V6 keyword、embedding、hybrid 保持 decision 98%、recall@3 97%、fact 97%，本轮 p95 分别为 28.5 ms、54.1 ms、41.2 ms，均通过 500 ms 门禁。
- 真实本地三服务浏览器验收完成文档上传、六阶段分析、个人二次发布、知识批准、未来 RAG 再召回和重复请求缓存命中；浏览器控制台无 warning/error。服务端日志同时暴露并推动修复了并发兼容列迁移的 `duplicate column` 竞态；除确定性回归测试外，使用全新 SQLite 对工单与审计端点执行 20 并发、40 请求复测，40/40 返回 200。截图保存在 `docs/images/interview/`。
- 本轮浏览器使用本地模板回答，证明授权、状态、证据、事务和降级链路，不作为外部模型质量证据。

2026-08-30 完成六阶段 Phase 1 强化验证：

- Agent Service 全量 127/127 通过。新增回归覆盖 objective 排序与跨租户过滤、冻结证据等待期间不漂移、阶段 1–4 原样恢复、无证据时文字确认不能扩大快照、四类 specialist 固定合并、单维失败隔离、显式冲突升级，以及两个请求竞争同一 resume token 时严格一个 200、一个 409。
- Media Service 在受支持的 Temurin JDK 18.0.2.1 下保持 108/108；默认 JDK 25 仍因现有 Mockito inline/ByteBuddy 不支持而报加载错误，该已知工具链边界不作为产品失败或通过证据。
- `contracts/http/analysis-session-v1.schema.json` 与 ADR-0009 固化 checkpoint version、evidence revision/hash、hybrid 检索、内部快照最小暴露和 CAS 语义；契约测试通过。
- V6 keyword/embedding/hybrid 保持 decision 98%、recall@3 97%、fact 97%，本轮 P95 分别为 14.9/29.0/19.2 ms。
- 新增 PRD V1 12 例门禁：decision、问题召回与精确率、objective Top-1、冲突、证据完整性、受支持结论、验收可测试性、检查点稳定和 specialist 顺序均为 100%，本轮多次验证 P95 为 17.22～25.08 ms。该集合无 holdout，不能外推真实 PRD 接受率。
- 统一 Web 完成 TypeScript 与 Vite 生产构建；分析页可查看 checkpoint version、evidence revision 与 hash 摘要。
- localhost-only 纵向验收扩展为 28 项并全部通过；新增 objective 证据快照、阶段恢复稳定和旧 resume token 409，原个人/团队发布、知识再召回、工单与播放链路保持通过。
- 仓库版与安装版 `enterprise-insight-maintainer` Skill 均通过 Skill Creator quick validation，并新增分析快照/CAS 不变量及 PRD 评测路由。
- 维护知识更新为 40 个批准来源、250 个 chunk；本轮复用 189 个未变化向量、重算 61 个变化 chunk，3/3 索引测试和漂移检查通过。

2026-08-30 完成知识生命周期 Phase 2 验证：

- Agent Service 全量 130/130 通过。新增回归覆盖 personal 替代与撤回、不可变 predecessor/successor 链、未来检索排除失效版本、历史聊天引用状态刷新、物理历史保留、图谱失效、team 生命周期四眼、跨 tenant 隐藏、重复决定 409，以及图谱重建失败时整笔事务回滚。
- 新增 `contracts/http/knowledge-lifecycle-v1.schema.json`，并扩展 approved knowledge、publication deliverables 与 evidence source 契约；JSON 解析、Pydantic 响应和契约测试通过。
- Knowledge Lifecycle V1 三类冻结场景全部通过，未来检索、版本链、历史状态、tenant 隔离、四眼、幂等冲突、图谱失效与物理保留九项均为 100%；模块拆分后的独立最终验收 P95 553.70 ms。该延迟包含完整 HTTP 分析/发布/知识治理流程，只是本机回归门禁，不是生产 SLO 或容量结果。
- V6 keyword/embedding/hybrid 保持 decision 98%、recall@3 97%、fact 97%，最终验收 P95 分别为 11.1/32.6/21.4 ms；PRD V1 十项质量指标保持 100%，P95 26.12 ms。
- localhost-only 纵向验收扩展为 33/33：新增个人替代链、撤回后的未来检索排除、历史引用状态、生命周期独立决定和 team 请求者禁止自批。Web TypeScript 与 Vite 生产构建通过。
- 历史引用回放只对升级后保存了来源快照的新日志完整生效；升级前 `sources_json` 为空的旧日志无法逆向恢复引用，不应包装成已迁移数据。
- 维护知识更新为 42 个批准来源、259 个 chunk；索引单测 3/3、语义查询命中 ADR-0010、仓库/安装 Skill quick validation 与知识漂移检查通过。

2026-08-31 完成行为保持的安全瘦身与理解入口验证：

- 未删除业务能力、HTTP/事件契约、安全边界、审批语义或质量门禁。持久化按变化原因拆分：`database.py` 的非空行由 1008 降至 584，`graph_store.py` 由 992 降至 792，`ticket_store.py` 由 800 降至 647；聊天观测、纯图谱抽取、工具审计分别进入独立模块。
- Web 的兼容入口 `api.ts` 非空行由 532 降至 188；JWT/transport、图谱、工单、观测请求进入领域 API 模块，现有调用方仍可从兼容 barrel 导入。新增 `docs/START_HERE.md`，按服务边界、症状和最小门禁给出十分钟阅读路径。
- 删除 Git 中 17,796,962 字节的历史演示 PDF；V2 seed/eval 已迁移到小型确定性 Markdown fixture，原二进制仍可从 Git 历史恢复。V2 的意图、回答/拒答、检索轮次与引用覆盖均为 100%，门禁通过。
- Agent Service 全量 130/130、Media Service 在 JDK 18 下 108/108、Web TypeScript/Vite 生产构建通过；V3 受控工具安全检查 100%、恰好一次违规 0，V6 三种检索模式保持 decision 98%、recall@3 97%、fact 97%，PRD V1 十项指标 100%，Knowledge Lifecycle V1 九项指标 100%。
- localhost-only 纵向验收 33/33 通过，仍只依赖临时 H2/SQLite、本机文件、随机 localhost 端口和 mock/local AI。仓库版与安装版维护 Skill quick validation 通过；语义知识查询已验证 revision 下的 miss→hit 缓存复用。

## 合并门禁

- 相关服务全量测试通过。
- Web 类型检查和构建通过。
- 契约校验、owner/tenant 负向测试通过。
- Agent 行为变化对应评测未退化。
- `python scripts/update_knowledge.py --check` 通过。
- 无法运行的验证必须说明环境原因、影响边界和替代证据。

## Agent 评测适用边界

- V6 黄金集包含 42 个手工案例和 4 份固定 fixture：37 个应回答、5 个应拒绝。当前显示的 98% decision 是 41/42 四舍五入，97% recall@3 与 fact 是 36/37 四舍五入，不是“98 个样本中答对 98 个”。
- `evaluate_v6.py` 显式关闭 LLM Router，使用确定性回答路径；judge 检查是否答/拒、Top-3 是否包含预期文档，以及答案是否包含任一期望事实子串。因此它是闭集检索/拒答回归门禁，不代表开放域模型准确率。
- PRD V1 黄金集包含 12 个手工场景，覆盖缺口等待、补充后恢复、objective Top-1、跨租户过滤、显式冲突、视频时间定位、引用支持、验收可测试性、阶段稳定和 specialist 固定顺序。当前质量项均为 100%，首次本机 P95 为 22.28 ms；样本规模小、与规则共同维护且没有真实客户 holdout，因此只能作为确定性回归门禁，不能外推 PRD 业务接受率或开放域模型能力。
- Knowledge Lifecycle V1 只有 personal 替代、personal 撤回、team 替代三类固定场景，用于防止治理语义回退；它不覆盖大规模图谱增量成本、长期数据保留策略或真实多人组织流程。
- 六阶段确认接口使用创建时的冻结证据并保留阶段 1–4；同一 resume token 的两个并发请求已有确定性回归，验证一次数据库 CAS 成功、另一次返回 409。它仍是业务阶段 checkpoint，不是模型调用中断后的执行栈恢复。

`.github/workflows/quality.yml` 将门禁拆为 Agent 全量用例 + V6 RAG + PRD V1 + Knowledge Lifecycle V1 + 维护索引单测与知识漂移、Media JDK 17 全量测试、Web 类型/生产构建和 localhost 平台 smoke。四个 job 独立暴露故障域，避免一个超长脚本掩盖具体失败位置。

## 不允许的质量声明

- mock 中间件通过不等于真实 Redis、MQ、对象存储或模型通过。
- 有 citation 字段不等于引用真实正确。
- UI 隐藏资源不等于完成授权。
- happy path 演示不等于任务具备重试、幂等和恢复能力。
