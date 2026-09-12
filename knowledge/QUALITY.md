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

2026-09-01 完成租户去重、任务 lease 与团队图谱范围修复：

- Agent Service 全量 131/131 通过；新增回归证明 team 图谱查询会读取同租户不同成员创建的实体，而 personal 查询不会越界。
- Agent V5 可观测性评测 8/8 检查通过（100%，p95 约 59.55 ms）；评测脚本显式使用测试 development auth mode，生产路径仍为 JWT-only。
- Media Service 在受支持的 Temurin JDK 18.0.2.1 下完整 Maven 测试 113/113 通过，其中 lease/Workflow 聚焦 19/19；新增条件 lease 完成/失败写入、内容 fan-out fencing、摘要前持续持有 lease，以及过期任务条件重入队的集成验证。
- Media Service 在当前 JDK 25 下仍因 Mockito inline/ByteBuddy 不支持该 Java 版本而无法启动部分测试；质量结论使用仓库声明支持的 JDK 18，不将 JDK 25 失败解释为产品回归。
- `mvn -q test` 在 `services/media-service`、Agent Service 全量回归和图谱聚焦回归均已执行；本次变更未引入公开 HTTP/事件契约变更。
- `python quality/agent-evals/evaluate_v5.py`、V6、PRD 和 Knowledge Lifecycle 评测均通过；本轮 `scripts/local_acceptance.py` 以 localhost-only 范围完成 33/33 检查，覆盖媒体→Agent outbox、时间证据、分析恢复、个人/团队隔离、审批、知识生命周期、工单、VIEWER 只读和缓存安全边界。
- pi-lens 当前会话诊断复核：24 个已诊断文件无剩余问题；此前提示的 54 条 ruff/pyright/ast-grep/LSP 诊断已由自动修复或格式化处理。
- 真实 Docker、Redis、RocketMQ、S3、外部模型和生产 IdP 仍不在本地验证范围；本次 acceptance 仅使用临时 H2/SQLite、本机文件、mock/local AI 和随机 localhost 端口。

2026-09-01 完成 P0/P1 上传、outbox 与结构化 LLM 通道加固：

- Agent Service 全量回归 **137/137** 通过；新增/更新的结构化响应、LLM client response format、兼容降级、路由契约和既有治理用例均通过。
- Media Service 的 outbox claim 聚焦回归 **3/3** 通过；覆盖单实例条件领取、过期 lease 接管、旧 worker fencing、失败退避和 DEAD 前的 attempt 条件。
- Outbox 状态现在由 `PENDING → CLAIMED → SENT/DEAD` 条件更新推进；这只证明 H2/JPA 代码和集成语义，正式 MySQL 方言、`SKIP LOCKED`/锁行为、告警和真实多实例故障注入仍未验证。
- Agent Router/Planner/Tool Agent 的 LLM 通道在 mock response 下验证 OpenAI strict JSON Schema、DeepSeek JSON Object、工具参数 JSON 字符串解码和规则降级；没有调用真实外部模型，因此不产生开放域质量或供应商兼容性通过证据。
- 本轮 V6 保持 keyword/embedding/hybrid 的 decision 98%、recall@3 97%、fact 97%，p95 分别为 13.2/27.4/24.1 ms；PRD V1 为 12/12、十项指标 100%，p95 19.38 ms；Knowledge Lifecycle V1 为 3/3、九项指标 100%，p95 487.00 ms。以上仍是固定 fixture 的确定性回归，不外推真实模型质量或生产容量。
- 本地验收脚本的测试视频改为带合法 MP4 `ftyp` 头的最小字节，并用显式 localhost HTTP 客户端代替可访问任意 scheme 的 URL opener；本轮修正随机 HS256 密钥长度和 Range 播放断言后，localhost-only 33/33 验收已通过。

2026-09-02 完成 P0/P1 变更后的最终 localhost 验收：

- `python scripts/local_acceptance.py` 返回 `PASS`，网络范围为 `localhost-only`，33 项检查全部通过。
- 验收覆盖注册与 Workspace、JWT tenant、Media 上传与 mock transcript、outbox delivery、Agent 检索、时间证据、分析等待/恢复、证据与 PRD 快照、发布/知识/工单审批、Range 播放、team 跨成员媒体和 Agent 检索、personal 隔离、team 四眼治理、VIEWER 只读、缓存授权边界、知识替代/撤回、历史引用状态和 resume token CAS。
- 视频证据成功保留时间范围 `start_ms=0`、`end_ms=5000`；上传 fixture 使用合法 MP4 `ftyp` 头，Range 响应断言验证头部字节而不是旧的明文测试内容。
- 本次验收使用临时 H2/SQLite、本机文件、随机 localhost 端口和 mock/local AI；它不证明真实 MySQL/Redis/RocketMQ/S3、外部 LLM、正式 IdP、生产容量或灾备能力。

2026-09-02 完成 P0/P1 变更后的最终回归复跑：

- Media Service 使用 Temurin JDK 18.0.2.1 执行 `mvn -q test`：113/113 通过，Failures 0、Errors 0、Skipped 0；此前失败的 JWT/Workspace 测试已更新为合法 MP4 `ftyp` fixture。
- V5 可观测性：8/8 检查通过，质量门禁通过，p95 chat latency 为 52.95 ms（门槛 ≤300 ms）。
- V6 固定黄金集：keyword、embedding、hybrid 均 decision 98%、recall@3 97%、fact 97%；p95 分别为 19.4 ms、34.6 ms、22.2 ms，门禁通过。
- PRD V1：12/12，decision、问题召回/精确率、objective Top-1、冲突、证据完整性、支持率、验收可测试性、checkpoint 稳定性和 specialist 确定性均为 100%，p95 为 43.58 ms，门禁通过。
- Knowledge Lifecycle V1：3/3，决策、未来检索、版本链、历史状态、tenant 隔离、四眼、幂等冲突、图谱失效和物理保留均为 100%，p95 为 627.47 ms，门禁通过。
- 以上结果均来自固定 fixture/黄金集和本机运行；V6 的 para-04 等已知边界样例仍按门禁规则记录，不外推开放域模型质量、真实用户接受率或生产容量。

2026-09-04 建立无需云服务器的本机准生产可靠性验证路径：

- 新增 MySQL 8.4、Redis 7、RocketMQ 5.2、MinIO、Media、Agent、Web 的 `compose.local-prod.yml`，以及 Toxiproxy 故障注入、Prometheus/Grafana、全链路烟测、开放模型并发浸泡、诊断采集和启停脚本。Compose、Prometheus YAML、k6 JavaScript、Python 探针和 PowerShell AST 均完成静态解析；当前主机没有 Docker/Podman 和 k6，尚未产生真实容器、中间件、故障注入或长时间浸泡通过证据。
- Media Service 修复本地锁表、登录限流表、JWT blacklist 的无界保留，并让工作流心跳调度器立即移除取消任务；对应单元回归通过。这些测试能证明已识别的引用保留路径被关闭，不能单独证明长期运行不存在其他泄漏。
- 上传接单改为同一数据库事务内提交任务与 `workflow_dispatch_outbox` 意图，调度采用 claim lease、fencing、退避和至少一次投递；新增集成测试证明 outbox 写入失败时任务同步回滚，并验证失败重试、过期 claim 接管和旧 worker fencing。公开上传响应仍返回可追踪 taskId，没有改变 HTTP 契约。
- Media Service 使用 Temurin JDK 18.0.2.1 全量 **124/124** 通过，Failures 0、Errors 0、Skipped 0；Agent Service 全量 **137/137** 通过；统一 Web 完成 TypeScript/Vite 生产构建。
- `scripts/local_acceptance.py` 再次以 `localhost-only` 范围通过 **33/33**，覆盖真实 JWT/tenant、上传、工作流、Media→Agent outbox、时间段证据、问答、分析恢复、审批发布、知识生命周期、工单和团队四眼治理。
- V5 可观测性 8/8 通过，p95 60.69 ms；V6 keyword/embedding/hybrid 均为 decision 98%、recall@3 97%、fact 97%，p95 分别为 34.5/51.1/32.8 ms；PRD V1 12/12 且十项指标 100%，p95 64.52 ms；Knowledge Lifecycle V1 3/3 且九项指标 100%，p95 746.20 ms。
- Agent `tracemalloc` 探针完成 100 次预热加 2,000 次同进程 Chat，GC 后净分配增长 99,364 bytes（约 0.095 MB），低于 24 MB 门槛；这是短时 Python 分配回归，不替代数小时 RSS/JFR/heap/线程与真实中间件联合分析。

2026-09-04 完成真实用户工作流复盘后的缺陷修复与生产能力显式化：

- 修复 `asset_ids` 误伤非视频来源的问题：视频选择现在只收窄视频证据，同一已授权 Workspace 内的上传文档与 `ACTIVE` 受治理知识继续参与检索。新增单元回归，并把 localhost-only 验收中的批准知识再查询改为携带已选视频，完整验收仍为 **33/33**。
- 媒体运行时契约新增 `transcriptMode` 与 `summaryMode`；Web 明确展示“验证模式/真实处理模式”，不再把 mock 转写与摘要包装成真实 AI。Auto 模式因未配置外部模型而正常本地降级时不再弹故障窗，显式 API 请求或真实 API 调用失败仍会告警。
- mock 转写不再把内部 `storagePath` 写入转写文本、跨服务事件和 Agent 证据；回归断言文件名仍可追踪，但存储路径不可见。
- DeepSeek 配置不再借用 `OPENAI_API_KEY`，空值和示例 key 不再被误判为可用模型配置；本机准生产脚本新增 `-RequireRealAi` fail-closed 门禁，在真实转写、摘要或 Agent 模型任一配置缺失时拒绝启动且不输出密钥。
- 本轮最终回归：Agent Service **142/142**，Media Service 在 Temurin JDK 18.0.2.1 下 **124/124**，Web TypeScript/Vite 生产构建通过；V6 三种检索模式保持 decision 98%、recall@3 97%、fact 97%，PRD V1 十项指标 100%，Knowledge Lifecycle V1 九项指标 100%。
- 真实外部转写、摘要和 Agent 模型联调仍未执行，因为当前没有经批准的供应商端点与凭据；`-RequireRealAi` 的缺配置失败路径已验证，但不将其包装成真实 AI 通过证据。

2026-09-04 完成生产试点基线落地后的最终本机回归：

- Agent Service 全量 **154/154** 通过，新增覆盖 MySQL SQL 兼容与生产配置 fail-closed、RS256/JWKS 验签、外部模型 tenant allowlist 和 180/365 天数据清理；Media Service 在 Temurin JDK 18.0.2.1 下全量 **131/131** 通过，Failures 0、Errors 0、Skipped 0，新增覆盖 OIDC 校验、RS256 签发、公钥 JWKS、模型出境门禁和 30/180 天媒体保留。
- 统一 Web 再次完成 TypeScript/Vite 生产构建；OIDC Authorization Code + S256 PKCE、外部令牌交换、生产关闭本地口令入口，以及过期媒体/转写的用户态展示均通过类型与打包门禁。
- `scripts/local_acceptance.py` 在随机 localhost 端口保持 **33/33**，继续覆盖真实平台 JWT/tenant、媒体上传、outbox、时间证据、问答、分析恢复、审批发布、团队四眼、受治理知识和工单；该脚本刻意使用 H2/SQLite 与 mock/local AI，不冒充 MySQL/Keycloak/外部模型集成结果。
- V5 可观测性 8/8 通过，p95 49.66 ms；V6 keyword/embedding/hybrid 均保持 decision 98%、recall@3 97%、fact 97%，p95 分别为 14.5/31.6/25.8 ms；PRD V1 12/12 且十项指标 100%，p95 20.14 ms；Knowledge Lifecycle V1 3/3 且九项指标 100%，最终复跑 p95 781.99 ms。
- `compose.local-prod.yml`、Keycloak realm、JSON Schema 和 PowerShell 启停/门禁脚本进入静态校验范围。当前主机仍没有 Docker/k6，故尚无真实 MySQL、Keycloak、Redis、RocketMQ、MinIO、多实例死锁、长时内存或容量 SLO 的运行证据；这些仍是上线前必须在具备对应运行时的机器补齐的环境门禁。

2026-09-07 接续额度中断的生产试点任务，完成会话续期与最终回归：

- OIDC 平台会话在到期前续签并重新查询当前 Workspace 成员角色；仅成员关系不存在的 404 可回退个人空间。新增前端 HTTP/存储模拟回归 **7/7**，覆盖 refresh token 轮换、并发 grant 合并、404 回退、401/403/500 不回退、登出期间迟到的供应商/平台响应及失效凭据清除。该套件使用真实前端模块，进入 CI 的 `npm test`，不冒充真实 Keycloak 浏览器联调。
- 新增 Media OIDC Workspace 交换测试 **4/4**：角色降级重新签发、无成员关系拒绝签发、未指定 Workspace 使用个人空间、无效外部身份拒绝进入授权流程。Media 全量在 Temurin JDK 18.0.2.1 下 **135/135** 通过，Failures/Errors/Skipped 均为 0；Agent 全量 **157/157** 通过，包含此前中断前补充的 MySQL 兼容、治理唯一槽位与保留期修复。
- Web TypeScript/Vite 生产构建通过；localhost-only 纵向验收 **33/33**，使用临时 H2/SQLite、本机文件、mock/local AI 和真实平台 JWT。验收输出保存于忽略的 `runtime/resume-local-acceptance.log`，Media 本轮输出在 `runtime/resume-media-tests.log`。
- V5 **8/8**；V6 keyword/embedding/hybrid decision **98%**、recall@3 **97%**、fact **97%**；PRD **12/12** 且十项指标 **100%**；Knowledge Lifecycle **3/3** 且九项指标 **100%**，门禁全部通过。维护索引测试 **3/3** 通过；Agent 全量内的备份回归验证临时 SQLite/媒体归档 SHA-256、quick_check、恢复与覆盖前安全备份。
- 12 份契约 JSON、准生产 Compose/CI YAML、Keycloak JSON 与 PowerShell 脚本完成语法解析。当前 Python 未安装额外 `jsonschema` 库，未宣称执行其元 Schema 校验；接口行为仍由 Agent/Media 契约与身份回归覆盖。
- 当前机器缺少 Docker/k6，真实 MySQL/Keycloak/Redis/RocketMQ/MinIO 运行、故障注入、生产数据库备份恢复及容量 SLO 仍待目标环境验证；没有调用外部模型供应商。轻量备份脚本不覆盖准生产 Docker 数据卷，此限制已加入运维知识。
- 知识更新器已重建当前状态与语义索引，`--check` 与补丁空白检查通过。

2026-09-11 收尾未入库工作，建立 lint 门禁并修复两处门禁缺陷：

- 新增仓库根 `ruff.toml`（ruff 0.16.6，E4/E7/E9/F/I/UP/B/RUF100，忽略 FastAPI 依赖注入惯用法 B008）与 `apps/web/eslint.config.js`（ESLint 10 flat config：`@eslint/js` recommended、typescript-eslint recommended、`react-hooks/rules-of-hooks`、`react-hooks/exhaustive-deps`、`react-refresh/only-export-components`）。CI 的 agent job 新增 `ruff check`，web job 新增 `npm run lint`。首次扫描 Python 110 条（101 条自动修复：导入排序、`datetime.UTC`、PEP 604/695 写法、无用 noqa；9 条手工处理 `zip(strict=)`、lambda 赋值与泛型语法），现为 0 条；ESLint 现为 0 error、18 warning（`exhaustive-deps` 与 fast refresh 提示保留为 warning）。未启用 eslint-plugin-react-hooks 7.x 的 React Compiler 校验规则集：本项目未使用 React Compiler，且其 `refs` 规则会把携带 ref 的 props 对象的全部属性读取误报为渲染期访问 ref（单个文件即 127 条误报）。
- 缺陷一：ruff F401 自动修复删除了 `graph_store.py` 对 `ENTITY_TYPE_LABELS` 的透传导入，而 `graph_rag.py` 仍从 `graph_store` 导入该符号，导致 `app.main` 无法加载、Agent 全量 14 个测试模块导入失败。修复为 `graph_rag.py` 直接从定义方 `graph_extraction.py` 导入。结论：自动修复之后必须重跑全量回归，lint 通过不等于行为保持。
- 缺陷二：PRD V1 门禁的 `prd-09-objective-ranking` 在没有可选本地 BGE 模型（`fastembed` 未安装，`requirements.txt` 亦不包含）时失败，`objective_recall1` 为 92%。用同一环境对上一次提交（2026-08-31）复跑同样失败，因此不是本轮回归，而是历史通过证据隐含依赖了本机可选模型；CI 环境同样只有哈希 embedding。根因：hybrid 在 RRF 平局（keyword 与 hash embedding 排名互为镜像）时以 0.5/0.5 融合门控分决胜，64 维哈希向量的噪声分反超了精确词项覆盖。修复为平局时先比较 keyword 覆盖分再比较融合分，门控分本身不变；新增回归 `HybridTieBreakTests`，已验证旧排序下该用例失败。
- 修复后本机回归（全部使用哈希 embedding，未安装 fastembed，`LLM_ROUTER_ENABLED=0`）：Agent 全量 **158/158**；V6 keyword/hybrid decision **98%**、recall@3 **97%**、fact **97%**，embedding-only 模式为 88%/84%/81%，低于其以本地 BGE 记录的 baseline，V6 门禁阈值只约束 hybrid，且该模式数字不代表真实模型质量；PRD **12/12** 且十项指标 **100%**；Knowledge Lifecycle **3/3** 且九项指标 **100%**；V5 **8/8**；维护索引测试 **3/3**。
- Media Service 在 CI 使用的 Temurin JDK 17.0.18 下 `mvn -q test` 全量 **135/135**，Failures/Errors/Skipped 均为 0；这是 JDK 17 口径的首次全量通过记录，JDK 18 口径以 2026-09-07 条目为准。Web `npm run lint` 0 error、`npm test` **7/7**、TypeScript/Vite 生产构建通过。
- `python scripts/local_acceptance.py` 返回 `PASS`，localhost-only **33/33**（临时 H2/SQLite、mock/local AI、随机端口、真实平台 JWT）。本机 Docker Desktop 已可用，`compose.local.yml` 的 agent、media、web 三容器构建后健康，`http://127.0.0.1:8080` 可访问；准生产 `compose.local-prod.yml`、k6 浸泡与故障注入仍未运行，真实中间件与外部模型结论不变。
- 面试文档中的测试数量已统一为 Agent 157（本条目后为 158）、Media 135；`PROJECT_CLOSEOUT.md` 与本文带日期的历史条目按规则保留当时数字。2026-09-01 至 09-11 的全部工作区改动已提交入库，Git 历史不再停留在 2026-08-31。

2026-09-12 架构优化阶段 1 首批落地（检索效率，见 `docs/ARCHITECTURE_OPTIMIZATION_PLAN.md` 第八节）：

- 新增 `app/text.py`（唯一分词器：`extract_search_terms`、停用词、CJK 窗口与锚点）与 `app/chunk_index.py`（授权 chunk 快照 + 预计算词项 + 词项倒排，按租户 revision 缓存）；`embeddings.py`、`rag.py` 中重复的 `normalize_text`、`char_ngrams`、`deduplicate_preserve_order` 与 CJK 窗口函数改为从 `app.text` 导入，`retrievers.py` 向后兼容地重导出旧符号。
- 关键词检索只对与 query 共享至少一个词项的 chunk 打分，其余按语料顺序补零分，排序与旧的逐块打分实现完全一致（新用例以暴力算法逐 query 对照）。hybrid 两路共用一次快照并以 2 线程并行；`RetrievalResult` 新增 `rerank_status`（disabled / applied / unavailable），精排配置了却失败时 trace 写 `rerank_skipped`（status=degraded），不再静默沿用融合榜。
- `system_meta` 增加 `content_revision:<tenant>`：租户写入只提升该租户与全局 revision，未指定租户的快照跟随全局；全局 bump（embedding 重建、保留清理）提升全部租户键。新增 `tests/test_chunk_index.py` 12 个用例覆盖倒排等价、精排状态与租户隔离失效。
- 本机回归（哈希 embedding，未安装 fastembed，`LLM_ROUTER_ENABLED=0`）：Agent 全量 **170/170**，ruff 0 告警；V6 hybrid decision **98%**、recall@3 **97%**、fact **97%**（与 2026-09-11 相同；单次运行 p95 由 8.6ms 变为 6.0ms，样本量小，只作参考）；PRD **12/12** 且十项指标 100%；Knowledge Lifecycle 门禁通过（p95 148.76ms）；V5 观测门禁通过（p95 14.87ms）。日志：`runtime/opt-stage1-gates.log`。Media、Web 与 localhost 验收本轮未改动、未重跑。
- 面试文档中的 Agent 测试数量已更新为 170；带日期的历史条目保留当时数字。

2026-09-12 架构优化阶段 0 首批落地（执行计划、执行器注册表、阶段耗时，见 `docs/ARCHITECTURE_OPTIMIZATION_PLAN.md` 第八节）：

- 新增 `app/architecture/planning.py`；`orchestration.py` 改为执行计划链 + 执行器注册表；`agentic_rag.py` 的路由 / 规划改写为链步骤并复用计划结果。`TraceStep.duration_ms`、`AgentSummary.execution_mode` / `clarify_question` 为新增字段，不删除任何契约字段。新增 6 个边界用例（计划可序列化、步骤可跳过、澄清不调处理器、工单直达计划、注册表拒绝重复与未知模式、计时器只给未计时步骤盖章）；两处旧用例对 agentic 处理器的精确调用断言改为接受 `plan=ANY`。
- 本机回归（哈希 embedding，未安装 fastembed，`LLM_ROUTER_ENABLED=0`）：Agent 全量 **176/176**，ruff 0 告警；V6 hybrid decision **98%**、recall@3 **97%**、fact **97%**（三次运行一致）；embedding-only 模式一次运行为 88%/81%/78%，随后两次重跑均为 88%/84%/81%，该模式不受门禁约束，波动原因未定位，如实记录；PRD **12/12**；Knowledge Lifecycle 门禁通过（p95 215.38ms）；V5 观测门禁通过（p95 20.40ms）。三套黄金集共 42 个问题经澄清门与工单直达判定扫描，无一误拦。日志：`runtime/opt-stage0-gates.log`。Media、Web 与 localhost 验收本轮未改动、未重跑。
- 面试文档中的 Agent 测试数量更新为 176。

2026-09-12 架构优化阶段 0 第二批落地（调用上限、证据字符预算、提示词外置、影子路由，见 `docs/ARCHITECTURE_OPTIMIZATION_PLAN.md` 第八节）：

- 新增 `app/call_limits.py`、`app/evidence_budget.py`、`app/prompts/`（10 个模板）；`llm_client`、`llm_router`、`llm`、`rag`、`agentic_rag`、`tools`、`planning`、`orchestration`、`routes/chat`、`chat_observability_store`、`database`、`models`、`manifest` 与 Web 监控面板同步改动。`chat_metrics` 新增 `execution_mode`、`shadow_mode`、`mode_agreement` 三列（`ensure_column` 兼容旧库），`ChatMetricsSummary` 新增五个字段，均为增量，不删除任何契约字段。新增 `tests/test_request_budgets.py` 23 个用例：计数器与降级路径（模型预算耗尽时路由退规则、答案退模板、工具记 `limited` 审计、未绑定请求不受限）、预算裁剪的顺序 / 句末 / 丢弃规则与单轮 / 多轮 trace、模板目录与占位符校验、影子路由规则与 `/metrics/summary` 一致率端到端。
- 本机回归（哈希 embedding，未安装 fastembed，`LLM_ROUTER_ENABLED=0`）：Agent 全量 **199/199**，ruff 0 告警；V6 keyword 与 hybrid decision **98%**、recall@3 **97%**、fact **97%**（hybrid p95 8.7ms），embedding-only 88%/84%/81%（与上一批的重跑值相同，不受门禁约束）；PRD **12/12** 且十项指标 100%（p95 6.97ms）；Knowledge Lifecycle 门禁通过（p95 179.97ms）；V5 观测门禁 8 项通过（p95 16.38ms）。证据预算在三套黄金集上未触发裁剪（文档切块 600 字符远小于 2200），因此三项指标与上一批完全一致是预期结果，不证明裁剪对质量无影响；长媒体转写片段是首个会触发它的场景。Web `npm run lint` 0 error / 18 warning（与改动前相同）、`npm test` **7/7**、TypeScript/Vite 生产构建通过。日志：`runtime/opt-stage0b-gates.log`、`runtime/opt-stage0b-web.log`。Media 与 localhost 验收本轮未改动、未重跑。
- 面试文档中的 Agent 测试数量更新为 199。

## 合并门禁

- 相关服务全量测试通过。
- `ruff check --config ruff.toml services/agent-service scripts quality` 与 `apps/web` 的 `npm run lint` 均为 0 error。
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

`.github/workflows/quality.yml` 将门禁拆为 Agent ruff lint + 全量用例 + V6 RAG + PRD V1 + Knowledge Lifecycle V1 + 维护索引单测与知识漂移、Media JDK 17 全量测试、Web ESLint + 前端单测 + 类型/生产构建，以及 localhost 平台 smoke。四个 job 独立暴露故障域，避免一个超长脚本掩盖具体失败位置。

## 不允许的质量声明

- mock 中间件通过不等于真实 Redis、MQ、对象存储或模型通过。
- 有 citation 字段不等于引用真实正确。
- UI 隐藏资源不等于完成授权。
- happy path 演示不等于任务具备重试、幂等和恢复能力。
