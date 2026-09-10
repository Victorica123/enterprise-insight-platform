# 运维知识

## 支持的本地工具链

- Media Service：以其 Maven 配置声明的 JDK 17/18 为准。
- Agent Service：Python 版本与依赖以 `services/agent-service` 的运行文件为准。
- Web：Node.js 版本与依赖以 `apps/web/package.json` 和锁文件为准。
- 静态检查：Python 在仓库根运行 `uvx ruff@0.16.6 check --config ruff.toml services/agent-service scripts quality`（或 `pip install ruff==0.16.6` 后运行同样的 `ruff check`）；Web 在 `apps/web` 运行 `npm run lint`。两者与 CI 使用同一配置，要求 0 error。使用 `--fix` 自动修复后必须重跑对应服务的全量测试。

核心验收必须可使用 H2、SQLite、本地媒体目录、mock 转写/摘要和 localhost HTTP 完成；外部模型、Redis、RocketMQ、S3 与正式域名属于独立的真实集成验证，不阻塞本地功能验收。

根目录提供可重复的本地纵向验收：

```powershell
python scripts/local_acceptance.py
```

脚本自动构建并启动两个后端到随机 `127.0.0.1` 端口，使用临时 H2、SQLite、本地媒体目录、mock 转写/摘要和本地模板回答；33 项检查覆盖个人全链路、第二用户团队创建/邀请/切换、跨成员视频与 Agent 共享、personal 隔离、团队四眼发布、知识物化与未来 RAG 再召回、知识替代/撤回/历史引用状态、团队生命周期四眼、工单交付、VIEWER 只读、缓存安全边界，以及 objective 证据快照、阶段恢复稳定和旧 resume token 的 CAS 拒绝。它不访问公网，也不要求 Docker、域名、Redis、RocketMQ、S3 或模型 Key。失败日志会保存在系统临时目录并打印路径。

维护知识索引使用以下命令，不依赖外部 embedding 服务：

```powershell
python scripts/knowledge_index.py query "JWT 与 tenant 如何隔离" --top-k 5
python scripts/knowledge_index.py stats
python scripts/update_knowledge.py
python scripts/update_knowledge.py --check
```

首次 query 写入已忽略的 `.codex-cache/`，相同 corpus revision 与 query digest 再次查询命中缓存；知识文件变化后 revision 自动更换。提交的是可再生语义索引，不提交查询缓存。

需要持久数据和统一浏览器入口时使用根目录 Compose：

```powershell
./scripts/start_local.ps1 -Build
# 浏览 http://127.0.0.1:8080
./scripts/stop_local.ps1
```

Web 只绑定 `127.0.0.1`，nginx 同源代理 `/agent` 与 `/media`；H2、SQLite 和媒体文件保存在已忽略的 `runtime/`。完整步骤见 `docs/LOCAL_RELEASE_RUNBOOK.md`。

需要在不租服务器的前提下验证真实中间件、并发和故障恢复时，使用隔离的准生产 Compose：

```powershell
./scripts/start_local_prod.ps1 -Build -Observability
k6 run quality/load/k6/e2e-smoke.js
k6 run quality/load/k6/platform-soak.js
./scripts/capture_local_diagnostics.ps1
```

准生产 Compose 默认允许 mock/local AI，以便离线验证状态机。要把一次运行计为真实 AI 联调，先在 `runtime/local-prod/.env` 配置 `LOCAL_PROD_TRANSCRIPT_*`、`LOCAL_PROD_SUMMARY_*` 和所选 Agent provider，再运行：

```powershell
./scripts/check_local_prod_ai.ps1 -EnvFile runtime/local-prod/.env
./scripts/start_local_prod.ps1 -Build -Observability -RequireRealAi
```

`-RequireRealAi` 会在启动 Docker 前检查真实转写、媒体摘要和 Agent 回答三条通道；任何 mock/local 模式、空值或模板凭证都会失败，且检查输出不会打印凭证。Media 的已鉴权 runtime 响应与 Web 视频工作台同时展示转写、摘要、调度和存储模式。

该栈在本机组装 Keycloak、三个独立 MySQL schema、Redis、RocketMQ、MinIO、两个后端和统一 Web，默认只绑定 loopback。启动脚本在忽略的 `runtime/local-prod/keys` 生成 RS256 密钥对，浏览器走 OIDC PKCE，Agent 通过 Media JWKS 验签；生产配置强制 Agent MySQL、模型 tenant allowlist 和 30/180/365 天保留任务。JVM 启用有界 JFR、NMT 退出统计和 OOM heap dump。`quality/memory/agent_tracemalloc_probe.py` 单独量化 Python 预热后的净分配增长。加 `-Faults` 启动 Toxiproxy 后，可用 `scripts/set_local_fault.ps1` 注入数据库、Redis、对象存储或 Agent 的延迟/断连。判定阈值、命令和证据边界见 `docs/LOCAL_RELIABILITY_RUNBOOK.md`。

统一 Web 本地启动：

```powershell
cd apps/web
npm ci
npm run dev
```

默认连接 `127.0.0.1:8081` 的 Media Service 与 `127.0.0.1:8000` 的 Agent Service；可分别用 `VITE_MEDIA_API_BASE_URL`、`VITE_API_BASE_URL` 覆盖。

## 配置原则

- 密钥只通过环境变量或密钥服务注入，不进入仓库和事件。
- JWT issuer/audience/signing trust、内部服务地址、队列和存储使用显式环境变量。
- 生产试点只把 RS256 私钥挂载给 Media；Keycloak 管理密码、数据库密码和模型凭证只进入忽略的 runtime env/secret store。
- 真实模型启动门禁还要求 `LOCAL_PROD_MODEL_EGRESS_ALLOWED_TENANTS` 非空，且每个值必须是已审批 Workspace tenant ID。
- 启动时验证关键配置，避免以不安全默认值静默进入生产模式。
- OIDC 页面在平台令牌到期前 60 秒自动续期，重新聚焦时再次检查；保留当前 Workspace 的请求由 Media 重新验证成员关系。IdP 会话失效后需重新登录；新增标签页或浏览器会话可能没有原标签页的 refresh token，不能仅凭 localStorage 中的平台令牌假定可持续续期。
- 开发 light/mock 配置与真实集成配置分开命名并在健康接口中可识别。

## 可观测性

- `trace_id` 从前端/网关贯穿媒体任务、事件投递、Agent 摄取、问答和工具调用。
- 指标至少覆盖队列积压、各阶段延迟、失败/重试、事件重复与冲突、引用验证失败、等待确认时长和审批结果。
- 错误对用户提供可操作原因，对日志保留结构化内部原因且不泄露敏感数据。
- 登录后可在统一 Web 的“监控”页查看 BGE 向量 LRU 与授权 Chunk 快照的命中率、请求、命中/未命中和容量，也可携带当前 Workspace Bearer JWT 调用 `GET /embeddings/status`。公开 `GET /system/status` 不返回这些流量指标。
- 缓存响应中的 `scope=process` 表示计数随 Agent 进程重启归零。请求数为 hits + misses；没有请求时前端显示 `—`，不能解释为 0% 命中。多实例环境必须按实例采集再聚合，当前实现不构成 Prometheus 接入或告警已上线的证明。

## 恢复策略

- 媒体任务可安全重试，不能重复创建资产；处理中的 worker 以可续租 fencing lease 保持所有权，reaper 只通过过期条件更新重新获得调度权。
- 上传接单、人工重试和 stale requeue 与 `workflow_dispatch_outbox` 在同一事务提交。dispatcher 对本地线程池拒绝或 MQ 发送失败做有上限的指数退避；成功响应表示“任务与调度意图已持久化”，不表示后台处理已完成。重复投递继续由任务 CAS/lease 保证安全。
- 转写事件可重放，Agent 消费必须幂等。Media outbox 采用至少一次投递语义，dispatcher 先以条件更新将 `PENDING`/过期 `CLAIMED` 领取为带 `claimId + claimExpiresAt` 的 `CLAIMED`，网络发送后的 `SENT/FAILED/DEAD` 也必须校验持有者和 lease；重复出站仍由下游幂等兜底。当前已完成 H2/JPA 集成回归，但正式多实例应继续验证数据库方言、锁行为、重试/DEAD 告警与故障注入。
- Agent 业务会话、阶段结果、人工答案和冻结证据 revision/hash 可持久化读回；确认保留阶段 1–4，只重算收敛与 PRD，并以数据库 CAS 原子消费 token。它仍不宣称执行栈级 checkpoint continuation。
- 发布 PRD、知识合并和外部写操作使用幂等键及审计记录；知识批准与 document/chunk/图索引同事务，失败回滚为 `PENDING`。
- 停止本地栈后可用 `python scripts/local_data.py backup` 创建带 SHA-256 manifest 的归档；`verify` 校验文件与 SQLite，`restore --force` 覆盖前自动创建 pre-restore 安全备份。
- 上述归档工具只覆盖轻量栈的 runtime 文件与 SQLite/H2；它不备份准生产 Docker 命名卷中的 MySQL、Keycloak 或 MinIO。准生产灾备须在目标主机另行完成数据库与对象存储备份、恢复及一致性演练。

## 当前运行状态与缺口

统一 localhost Compose、启动/停止脚本、备份校验恢复工具、本地发布手册和本地质量目标已提供。无容器验收链路已实际通过；准生产 Compose、k6、JFR/NMT、tracemalloc 和 Toxiproxy 入口也已提供。当前主机没有 Docker/k6，因此准生产配置只完成静态解析，不能声明真实容器、中间件或故障注入已经运行通过。

真实 Redis、RocketMQ、MySQL、S3 与 Keycloak 的可重复本机验证路径已经定义，但仍需在安装 Docker/k6 的主机执行并留存结果；外部模型 smoke、生产数据库迁移编排、灾备演练与监控告警接入仍待目标环境验证。两个 outbox 的 claim/lease 已在 H2/JPA 集成测试验证，但尚未在真实数据库、多实例和故障注入环境验证；当前实现仍应按至少一次投递、消费者幂等来理解。`docs/SLO.md` 已记录获批的生产试点目标，但在取得目标环境观测证据前不能宣称已经兑现。
