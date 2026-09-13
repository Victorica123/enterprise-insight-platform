# 本机准生产可靠性验证

这套验证不需要云服务器：服务和真实中间件都运行在开发机的 Docker 网络内，只把 UI、诊断和对象存储端口绑定到 `127.0.0.1`。它验证部署前的代码行为，但不替代异机网络、云盘性能、真实模型配额和多可用区演练。

## 验证层级

| 层级 | 命令 | 能证明什么 |
|---|---|---|
| 零依赖功能验收 | `python scripts/local_acceptance.py` | JWT/tenant、上传、证据摄取、问答、分析、审批、发布等主链路 |
| 本机准生产 | `./scripts/start_local_prod.ps1 -Build -Observability` | Keycloak OIDC、RS256/JWKS、Media/Agent MySQL、Redis、RocketMQ、MinIO、两个后端和统一前端的真实组装 |
| 完整目标环境验收 | `python scripts/local_acceptance.py --external` | 复用已启动容器，Keycloak PKCE 登录及 42 项个人/团队业务验收 |
| 全链路烟测 | `k6 run quality/load/k6/e2e-smoke.js` | OIDC PKCE→上传→异步处理→Agent 摄取→带时间段证据问答 |
| 并发浸泡 | `k6 run quality/load/k6/platform-soak.js` | 上传接单稳定性、队列积压、Agent/MySQL 并发、延迟和错误率趋势 |
| Python 分配探针 | `python quality/memory/agent_tracemalloc_probe.py` | 同进程重复真实 Chat 调用后的 Python 净分配增长 |
| 故障注入 | `./scripts/start_local_prod.ps1 -Build -Faults` | MySQL/Redis/MinIO/Agent 延迟或断连时的超时、恢复与补偿行为 |

## 一键运行

先安装 Docker Engine（Compose v2）和 k6，然后在仓库根目录执行：

```powershell
./scripts/run_local_reliability.ps1 -Build
```

默认运行一次全链路烟测、10 分钟并发浸泡、停止施压后的任务排空检查、Agent `tracemalloc` 探针和诊断采集。缩短或加大压力可通过环境变量控制：

运行器通过 `scripts/local_oidc.py` 在本机 Keycloak 创建独立测试账号，凭据只写入忽略的 `runtime/local-prod/load.env` 并传给 k6。单独运行 k6 前需将该文件加载为进程环境变量。每个 VU 走 Authorization Code + S256 PKCE，约四分钟后重新授权；不启用生产禁用的本地注册或用户密码 grant。`--external` 也会创建独立测试用户与业务数据，不启动或关闭现有服务；应只对专用测试栈使用。

```powershell
$env:SOAK_DURATION = "30m"
$env:CHAT_VUS = "48"
$env:UPLOAD_RATE = "16"
$env:DRAIN_TIMEOUT_SECONDS = "1200"
./scripts/run_local_reliability.ps1
```

结果保存在 `runtime/local-prod/results/`，诊断快照保存在 `runtime/local-prod/diagnostics/`。Media JVM 会持续保留最近 30 分钟、最大 256MB 的 JFR；OOM 时自动写 heap dump。`capture_local_diagnostics.ps1` 还会采集容器资源、Java thread dump、Redis memory、任务/outbox 积压和 InnoDB 状态；检测到 JVM deadlock 时整次运行直接失败。

## 故障演练

使用 Toxiproxy 覆盖启动：

```powershell
./scripts/start_local_prod.ps1 -Build -Faults
./scripts/set_local_fault.ps1 -Target agent -Mode latency -LatencyMs 2000
./scripts/set_local_fault.ps1 -Target minio -Mode down
./scripts/set_local_fault.ps1 -Target minio -Mode reset
```

`Target` 支持 `mysql`、`redis`、`minio`、`agent`。RocketMQ 可直接用 Compose 暂停/恢复 broker，再观察 `workflow_dispatch_outbox` 与 stale-task reaper 是否恢复积压任务：

```powershell
docker compose --env-file runtime/local-prod/.env -f compose.local-prod.yml stop rocketmq-broker
docker compose --env-file runtime/local-prod/.env -f compose.local-prod.yml start rocketmq-broker
```

## 判定标准

- 烟测的全部 check 必须为 100%。
- 浸泡期间上传与 Chat 的 HTTP 失败率应低于 1%，P95 分别低于 2s/3s；若机器资源较弱，可调整吞吐，但不要放宽失败率来掩盖错误。
- 高峰时 `workflow_dispatch_outbox` 可以短暂积压，但停止施压后应持续下降；任务不应长期停留在 `QUEUED`、`TRANSCRIBING` 或 `SUMMARIZING`。
- thread dump 中不得出现 JVM deadlock；InnoDB 状态不得持续出现同一事务死锁。单次死锁被事务安全重试并不等同于系统死锁，但必须能解释和量化。
- 用同一负载做至少三个时间窗口的内存基线：预热后、压力结束、完整 GC/静置后。只看 RSS 峰值不能判定泄漏；应结合 JFR、heap dump/类直方图、tracemalloc 净增长和缓存上限。
- 故障恢复后，Outbox/reaper 应使已提交任务继续推进，不能出现“接口返回失败但数据库里留下无 taskId 可追踪任务”的半成功。

## 当前边界

2026-09-13 已在独立 `codex-stage4-f4819d11` 环境运行真实 MySQL 8.4、Redis、RocketMQ、MinIO：42/42 业务验收、MySQL 迁移专项、分片续传与 Range、Agent 断连恢复、两库备份还原均通过。有限 k6 为 3 VUs、150 HTTP 请求、0 失败、p95 52.01 ms。该环境使用真实 HS256 JWT 与 mock/local AI，未使用下面默认准生产栈的 Keycloak/RS256 路径，也未运行 10 分钟浸泡、全套 Toxiproxy/JFR/NMT 或多实例故障演练。精确证据见 `knowledge/QUALITY.md`，不可当作生产 SLO 或真实模型质量。

Media 已使用 Flyway V1/V2，Agent 已有八项编号迁移；旧 Media 库先备份并在副本通过冻结 V1 校验后显式 baseline，升级后禁回 `ddl-auto=update`。操作步骤见 `docs/LOCAL_RELEASE_RUNBOOK.md`。本机已安装 Docker/k6；后续缺口是目标环境证据，不是这些工具缺失。

默认准生产栈使用真实 Keycloak/MySQL/Redis/RocketMQ/MinIO，但转写、摘要和 Agent 回答仍可使用本地确定性实现。首次启动会在 `runtime/local-prod/keys` 生成 RS256 密钥对；Keycloak 管理密码只保存在忽略的 `.env`。浏览器在 `http://127.0.0.1:18082` 完成 OIDC PKCE，Media 把外部身份映射到内部 Workspace，Agent 从 `/api/auth/jwks` 验证平台令牌。新用户应先以本地 AI 模式登录一次，让系统创建 Workspace，再从界面会话/运行信息取得 tenant ID 并完成数据出境审批；之后在 `runtime/local-prod/.env` 补齐 `LOCAL_PROD_TRANSCRIPT_*`、`LOCAL_PROD_SUMMARY_*`、所选 Agent provider 和 `LOCAL_PROD_MODEL_EGRESS_ALLOWED_TENANTS`，先执行 `./scripts/check_local_prod_ai.ps1 -EnvFile runtime/local-prod/.env`，再用 `./scripts/start_local_prod.ps1 -Build -RequireRealAi` 重启。门禁不会打印凭证，并拒绝 mock 转写、本地回答、空值、模板值或空出境白名单；模型限流、供应商网络、数据处理协议和成本风险仍必须另做小流量验证。

停止环境：

```powershell
./scripts/stop_local_prod.ps1
```

只有明确不再需要测试数据时才使用 `-Purge`；它会删除 Docker named volumes。
