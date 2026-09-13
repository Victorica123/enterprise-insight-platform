# 运维知识

## GitHub 源码托管（2026-09-13）

仓库为 [Victorica123/enterprise-insight-platform](https://github.com/Victorica123/enterprise-insight-platform)，可见性为私有，默认分支为 `main`。本地 `origin` 使用 `https://github.com/Victorica123/enterprise-insight-platform.git`；日常提交后运行 `git push origin main`。托管基线包含检索与通道隔离修复 `ee51a8e` 及其完整 Git 历史。

真实 `.env`、`runtime/`、`backups/`、依赖与构建目录继续按现有忽略规则留在本机。早期误跟踪的 Media 编辑器设置和 7 份演示上传/临时视频已从当前版本索引移除，本机文件与历史版本均保留。首次托管前检查了工作树与历史 blob 中的常见凭证模式和大文件；命中的示例占位值与代码表达式已人工复核。

`.github/workflows/quality.yml` 在 push / pull request 时运行 Agent、Media、Web 和 localhost smoke 四组检查。最新本地验证见 `QUALITY.md`；GitHub 上的每次执行结果以仓库 Actions 页面为准。本机 Compose 的镜像、数据和恢复材料仍按下方部署记录管理。

## 当前本机部署（2026-09-13）

阶段 0–4 代码提交 `af2dc6e` 已部署到既有 Compose project `enterprise-insight-local`，入口 **http://127.0.0.1:8080**。nginx 同源修复为 `daa29bf`，播放代理前缀修复为 `03f810b`；Web 使用最后的修复镜像，两个后端保持架构提交对应镜像。三个容器均 healthy，仅 Web 发布 loopback 8080，`erp-mssql` 未改动。该次本机部署时尚未配置 remote；当前托管状态见上方 GitHub 记录。

| 服务容器 | 固定镜像 | 已核对 Image ID（前 12 位） |
| --- | --- | --- |
| `enterprise-insight-local-web-1` | `enterprise-insight-local-web:release-03f810b` | `39c308d4bca2` |
| `enterprise-insight-local-media-1` | `enterprise-insight-local-media:release-af2dc6e` | `fae401c1022d` |
| `enterprise-insight-local-agent-1` | `enterprise-insight-local-agent:release-af2dc6e` | `8e6d45906b65` |

本机使用文件 H2、SQLite、local 存储、HS256 JWT、mock 转写/摘要和 local Agent。Media 已执行显式 V1 baseline→V2，最终 `MEDIA_FLYWAY_BASELINE_ON_MIGRATE=false`、`SPRING_JPA_HIBERNATE_DDL_AUTO=validate`；Agent ledger 为 8。这不是 Keycloak 或外部模型发布。

发布材料位于 `backups/local-release-20260913-132509/`：`pre-upgrade.zip` 已校验 516 文件；`compose-deployed.json` 固定当前三份镜像与目标环境；`compose-rollback.json` 保留旧镜像及升级前环境。完整 Image ID 与过程状态见 `runtime/codex-local-release-state.json`。这些本机文件含部署凭证，保持在忽略目录内。升级前旧镜像保留为 `enterprise-insight-local-{web,media,agent}:pre-20260913-132509`，不要只切旧镜像而继续使用新 schema。

先在数据副本、再在目标库停写升级，均在恢复 Web 写入前逐表核对原字段/行数/内容摘要；原 H2 为 9 表/0 行，SQLite 为 16 表/1 行。副本 project `codex-release-20260913132509` 已关闭并移除容器/网络，保留副本文件。正式部署之后新增了验收账号与示例数据，恢复升级前备份前必须先保留这些新写入；本轮未对正式本机执行降级回退。

发布验收：Web 26/26、实际入口带 Origin 的业务链路 42/42、同源检查 5/5；浏览器登录、3 秒 MP4/206 回放、阶段日志、SSE 证据与六路由宽窄屏通过。快速复核用 `python scripts/check_local_web.py`；该命令不创建账号或修改数据。nginx 保留 Host 的外部端口，播放客户端保留 `/media` 路径前缀，不能用只测后端直连接口代替浏览器检查。后续维护从 harness brief、本文与 `QUALITY.md` 最新条目恢复，原迁移来源只读，既有一次性备份/副本脚本不要重跑覆盖。

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

脚本自动构建并启动两个后端到随机 `127.0.0.1` 端口，使用临时 H2、SQLite、本地媒体目录、mock 转写/摘要和本地模板回答；42 项检查覆盖个人/团队隔离、视频证据、分析冻结与恢复、审批、知识生命周期、工单、缓存、SSE/连续指代，以及阶段记录的实际执行/分页/越权和有聊天数据后的监控聚合。脚本显式清空 Agent MySQL URL、固定 H2/HS256 并关闭 LLM Router，避免继承真实环境配置。它不要求 Docker、域名或模型 Key；失败日志会保存在系统临时目录并打印路径。

维护知识索引使用以下命令，不依赖外部 embedding 服务：

```powershell
python scripts/knowledge_index.py query "JWT 与 tenant 如何隔离" --top-k 5
python scripts/knowledge_index.py stats
python scripts/update_knowledge.py
python scripts/update_knowledge.py --check
```

首次 query 写入已忽略的 `.codex-cache/`，相同 corpus revision 与 query digest 再次查询命中缓存；知识文件变化后 revision 自动更换。提交的是可再生语义索引，不提交查询缓存。

知识来源按仓库相对 POSIX 路径字符串排序，避免 Windows/Linux 的 `Path` 大小写比较差异改变 manifest 与 revision。跨平台生成后必须通过同一 `scripts/update_knowledge.py --check`；大小写混合路径的回归位于 `scripts/tests/test_knowledge_index.py`。

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

Web 使用 `#/media`、`#/qa`、`#/analysis`、`#/tickets`、`#/graph`、`#/monitor` 六个路由，支持浏览器前进/后退与深链接刷新。Query 的 staleTime 为 15 秒、无观察者缓存保留 5 分钟，读请求最多重试两次；普通 4xx 与取消不重试，408/429 可退避。任务轮询随无进展时间由 2/5/10 秒延长到 30 秒，终态停止。写操作不自动重放。身份/Workspace/角色变化会取消并清空旧 QueryClient，QA 会话在同一 Workspace 内跨页面保留。

## 配置原则

- 密钥只通过环境变量或密钥服务注入，不进入仓库和事件。
- JWT issuer/audience/signing trust、内部服务地址、队列和存储使用显式环境变量。
- 生产试点只把 RS256 私钥挂载给 Media；Keycloak 管理密码、数据库密码和模型凭证只进入忽略的 runtime env/secret store。
- 真实模型启动门禁还要求 `LOCAL_PROD_MODEL_EGRESS_ALLOWED_TENANTS` 非空，且每个值必须是已审批 Workspace tenant ID。
- 启动时验证关键配置，避免以不安全默认值静默进入生产模式。
- OIDC 页面在平台令牌到期前 60 秒自动续期，重新聚焦时再次检查；保留当前 Workspace 的请求由 Media 重新验证成员关系。IdP 会话失效后需重新登录；新增标签页或浏览器会话可能没有原标签页的 refresh token，不能仅凭 localStorage 中的平台令牌假定可持续续期。
- 开发 light/mock 配置与真实集成配置分开命名并在健康接口中可识别。

## Agent 启动、迁移与并发

从 `services/agent-service` 运行 `python -m app.serve`；容器使用同一入口。配置集中在 `app/config.py`，启动校验失败时只输出参数名和原因。原 getter API 保留；修改部署配置后重启服务，不把测试用的环境缓存失效机制当作在线配置管理。

| 参数 | 默认值 | 运行含义 |
| --- | --- | --- |
| `AGENT_WORKERS` | 1 | uvicorn 进程数；Compose 可用 `LOCAL_AGENT_WORKERS` 传入 |
| `AGENT_THREAD_POOL_SIZE` | 40 | 每进程同步 HTTP / SSE 阻塞阶段共用的 anyio 线程额度 |
| `AGENT_SPECIALIST_WORKERS` | 4 | 每进程确定性领域执行器线程上限 |
| `HYBRID_CHANNEL_WORKERS` | 4 | 每进程 keyword/embedding/rerank 各自的在途上限，无额外排队额度；默认合计最多 12 |
| `HYBRID_CHANNEL_TIMEOUT_SECONDS` | 2 | 每条召回通道从提交到完成的独立截止 |
| `HYBRID_RERANK_TIMEOUT_SECONDS` | 3 | 可选精排的截止，超时保留精排前顺序 |
| `HYBRID_KEYWORD_MIN_RATIO` | 0.35 | 关键词通道相对于最高原始分的下限 |
| `HYBRID_SEMANTIC_MIN_SCORE` / `HYBRID_HASH_MIN_SCORE` | 45 / 10 | 0–100 分数下限；不得把真实语义阈值直接用于 hash |
| `CONVERSATION_LEASE_SECONDS` | 120 | 每三分之一周期续租，过期轮次不得复活 |
| `EMBEDDING_REBUILD_BATCH_SIZE` | 64 | 后台补齐批次，后台循环最多 512 条 |
| `EMBEDDING_BACKFILL_INTERVAL_SECONDS` | 60 | 后台补齐周期，推理不占数据库写事务 |

每个 worker 有独立模型、缓存、指标和后台循环；增加进程前先量测内存、数据库竞争与真实吞吐。缓存依靠持久化 revision 失效，会话依靠数据库 CAS，不能把进程内缓存当作分布式锁。

检索通道的 `timeout` 不代表原生推理被终止：该任务继续占槽直到退出，持续卡住会使后续同通道立即返回 `saturated`，其他通道仍可提供合格证据。排障看 `retrieval_keyword*` / `retrieval_embedding*` trace 的状态、耗时和原始/接受/保留数，再按需要重启 Agent；勿用不断创建新线程绕过容量。配置变更后重启服务。hash 路径明确记录 `keyword_then_hash`，真实语义路径为 `rrf`；这些状态不能被混记为真实模型验收。

`database.init_db()` 通过编号迁移和 `schema_migrations` 升级。SQLite 用 `BEGIN IMMEDIATE`，失败整体回滚；MySQL 用 advisory lock，DDL 自动提交，迁移必须可重试。升级前先停写并备份，先在数据库副本演练；未来变化追加迁移。若数据库版本未知或高于应用，启动会拒绝，勿手改 ledger 绕过。blob/JSON 双写只保障向量读兼容，不代表整个数据库可随意降级。

当前有八项编号迁移。`m008_mysql_text_fields` 只在 MySQL 将 `analysis_sessions.asset_ids_json`、`tickets.source_document_ids`、`knowledge_lifecycle_requests` 的 reason/replacement_statement/replacement_evidence_json、`knowledge_versions.invalidation_reason`、`documents.lifecycle_reason` 升级为 LONGTEXT；SQLite no-op。迁移可在部分 DDL 已提交后重入，1–7 的编号与实现不重写。MySQL 8.4 旧库/新库、双进程初始化、重启、长文本和未知版本拒绝已在隔离测试库验证；目标业务库仍需自己的副本演练与备份。

SSE 网关需要允许长连接并关闭响应缓冲；服务返回 `X-Accel-Buffering: no` 和 15 秒心跳。只有 `done` 是完整回答；断连后需由用户重新提问，服务不透明重放工具请求。会话冲突可重试或新建会话，不能清除他人的活跃租约。

## Media 配置、迁移与阶段查询

十二组配置通过各自原 `app.*` 前缀独立绑定，`AppProperties` 只保留兼容聚合；原环境变量继续有效。配额、租约和完成事务分别在 `TaskQuotaService`、`TaskLeaseService`、`TaskCompletionService`，故障排查按职责定位。

H2/MySQL 使用 `db/migration/{vendor}` 的 Flyway V1/V2，Hibernate 固定 `ddl-auto=validate`。空库直接应用 V1/V2。没有 `flyway_schema_history` 的旧库默认拒绝自动接管；先停写、备份并在副本演练，只有旧库满足冻结 V1 的表/列/主键/唯一约束后才可临时设置 `MEDIA_FLYWAY_BASELINE_ON_MIGRATE=true`，登记 V1 baseline 并执行 V2。两个 Compose 都传递该变量。接管后恢复 false，核对历史与业务数据并重启验证；禁止 clean、手改 ledger、自动 repair 或通过 `ddl-auto=update` 绕过失败。未知未来版本拒绝启动，回退需匹配版本的数据备份，不能直接以旧应用打开新库。

已鉴权 `GET /api/workflow/tasks/{taskId}/stages?after=0&limit=50` 返回真实执行记录；limit 为 1–100，按 ID 排他游标翻页。错误仅为固定错误码；audit-days 控制清理。任务处理恢复把旧处理阶段标为 ABANDONED，独立 DELIVERY 不在此恢复范围，硬崩溃残留 RUNNING 不能当作仍在执行的充分证据，需结合 outbox 状态排障。

Agent 投递由持久 outbox 重试，客户端每次只发送一次。默认 `APP_AGENT_CIRCUIT_FAILURE_THRESHOLD=3`、`APP_AGENT_CIRCUIT_OPEN_MS=30000`、`APP_AGENT_CIRCUIT_MAX_OPEN_MS=300000`；半开只放行一个探测，熔断跳过不增加 attempt。熔断状态为实例内状态，重启后重建；恢复可靠性依赖数据库 outbox 与下游幂等，不依赖熔断状态持久化。

## 可观测性

- `trace_id` 从前端/网关贯穿媒体任务、事件投递、Agent 摄取、问答和工具调用。
- 指标至少覆盖队列积压、各阶段延迟、失败/重试、事件重复与冲突、引用验证失败、等待确认时长和审批结果。
- 错误对用户提供可操作原因，对日志保留结构化内部原因且不泄露敏感数据。
- 登录后可在统一 Web 的“监控”页查看 BGE 向量 LRU 与授权 Chunk 快照的命中率、请求、命中/未命中和容量，也可携带当前 Workspace Bearer JWT 调用 `GET /embeddings/status`。公开 `GET /system/status` 不返回这些流量指标。
- 缓存响应中的 `scope=process` 表示计数随 Agent 进程重启归零。请求数为 hits + misses；没有请求时前端显示 `—`，不能解释为 0% 命中。多实例环境必须按实例采集再聚合，当前实现不构成 Prometheus 接入或告警已上线的证明。

## 恢复策略

- 媒体任务可安全重试，不能重复创建资产；处理中的 worker 以可续租 fencing lease 保持所有权，reaper 只通过过期条件更新重新获得调度权。
- 上传接单、人工重试和 stale requeue 与 `workflow_dispatch_outbox` 在同一事务提交。dispatcher 对本地线程池拒绝或 MQ 发送失败做有上限的指数退避；成功响应表示“任务与调度意图已持久化”，不表示后台处理已完成。重复投递继续由任务 CAS/lease 保证安全。
- 转写事件可重放，Agent 消费必须幂等。Media outbox 采用至少一次投递语义，dispatcher 先以条件更新将 `PENDING`/过期 `CLAIMED` 领取为带 `claimId + claimExpiresAt` 的 `CLAIMED`，网络发送后的 `SENT/PENDING/DEAD` 也必须校验持有者和 lease；重复出站仍由下游幂等兜底。当前已有 H2/JPA 回归和真实 MySQL 单实例断连恢复证据，正式多实例仍需验证竞争领取、锁行为与重试/DEAD 告警。
- Agent 业务会话、阶段结果、人工答案和冻结证据 revision/hash 可持久化读回；确认保留阶段 1–4，只重算收敛与 PRD，并以数据库 CAS 原子消费 token。它仍不宣称执行栈级 checkpoint continuation。
- 发布 PRD、知识合并和外部写操作使用幂等键及审计记录；知识批准与 document/chunk/图索引同事务，失败回滚为 `PENDING`。
- 停止本地栈后可用 `python scripts/local_data.py backup` 创建带 SHA-256 manifest 的归档；`verify` 校验文件与 SQLite，`restore --force` 覆盖前自动创建 pre-restore 安全备份。
- 上述归档工具只覆盖轻量栈的 runtime 文件与 SQLite/H2；它不备份准生产 Docker 命名卷中的 MySQL、Keycloak 或 MinIO。准生产灾备须在目标主机另行完成数据库与对象存储备份、恢复及一致性演练。

## 当前运行状态与缺口

2026-09-13 在独立 Compose project 上完成 MySQL 8.4、Redis、RocketMQ、MinIO 的 42 项纵向验收、Agent 断连恢复和有限 k6 冒烟；两个 MySQL 业务库停止应用写入后，备份校验并恢复到新 schema，33 表/518 行摘要一致。完整结果与本机日志见 `knowledge/QUALITY.md`。原 `enterprise-insight-local` 与 `erp-mssql` 未升级或停止。

本机已安装 Docker/k6；本轮身份为 HS256，AI 为 mock/local。Keycloak/RS256、外部模型、长时间压力、JFR/NMT/tracemalloc 浸泡、多 Media 实例竞争、MinIO 对象和异机灾备、聚合告警仍需独立演练。MySQL 的本机迁移/还原不替代目标业务库升级与匹配版本回退；至少一次投递与消费者幂等语义保持不变。`docs/SLO.md` 中的生产试点目标尚无兑现证据。
