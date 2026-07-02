# 压测指南：MQ 开/关量化对比（P2）

> 目标：用同一负载压两轮 —— `app.mq.enabled=false`（本地 `@Async`）vs `=true`（RocketMQ）——
> 用 P50/P99、错误率、吞吐、积压曲线量化「MQ 异步削峰」到底带来了什么、代价是什么。

## 原理：对比的到底是什么

两种模式的**处理能力完全相同**（同一个 `videoTaskExecutor`：core2/max4/queue50，同样的转写耗时），
差别只在**提交请求后、开始处理前**这一段：

| | MQ 关（本地 @Async） | MQ 开（RocketMQ） |
|---|---|---|
| 上传接口做什么 | `publish()` 直接把任务投进线程池 | `syncSend` 毫秒级投给 broker |
| 积压放在哪 | JVM 内队列（上限 50） | broker（磁盘，几乎无上限） |
| 超限会怎样 | `TaskRejectedException` → 用户收到 **500** | 消费端拒收 → broker **重投递**，用户无感 |
| 代价 | 高峰期直接拒单 | 端到端延迟拉长（排队转移到 broker） |

> 关键前提：Mock 转写默认**瞬间返回**，线程池永不饱和，两种模式测不出差异。
> 压测必须设 `APP_TRANSCRIPT_MOCK_DELAY_MS`（如 5000 = 5s/任务）还原真实转写的
> 慢消费者特征，**两轮用同一值**保证公平。

## 前置条件

- Docker Desktop 运行中
- [k6](https://k6.io/)：`winget install k6` 或 `choco install k6`
- 压测入口是 `POST /api/media/upload/file`（单文件上传）：一次请求触发完整
  「存盘→建任务→publish→异步处理」链路，且不带 MD5 → 无去重/单飞干扰，A/B 只剩一个变量

## 跑法

### 0）起可观测栈（两轮共用，全程别停）

```bash
docker compose --profile observability up -d
```

- Prometheus: <http://localhost:19090>（宿主机 9090 落在 Windows 保留端口段，同 redis 6379→7379 先例映射到 19090）
- Grafana: <http://localhost:3000>（免登录）→ 仪表盘「视频平台 · MQ 开/关 A/B 压测对比」

### 1）轮 1：MQ 关

```powershell
# PowerShell（默认 MySQL+Redis 模式，Spring Boot 自动拉起容器）
$env:APP_TRANSCRIPT_MOCK_DELAY_MS="5000"; mvn spring-boot:run
```

```bash
# 另一个终端
k6 run loadtest/upload-load.js
```

跑完停掉应用（Ctrl+C）。

### 2）轮 2：MQ 开

```powershell
docker compose --profile mq up -d        # RocketMQ namesrv + broker
$env:APP_TRANSCRIPT_MOCK_DELAY_MS="5000"; $env:APP_MQ_ENABLED="true"; mvn spring-boot:run
```

```bash
k6 run loadtest/upload-load.js
```

### 3）看图对比

打开 Grafana 仪表盘，把时间范围拉到覆盖两轮压测。所有序列带 `mq=false|true` 标签，
同一面板直接对比两段时间窗。

k6 可调参数（环境变量）：`VUS`（默认 10）、`RAMP`/`HOLD`（默认 20s/2m）、`THINK`（默认 0.5s）、
`FILE_KB`（默认 64）、`BASE_URL`、`K6_USER`/`K6_PASS`。

## 判读指南（按面板）

1. **上传接口响应时间分位数** — 两轮成功请求都应是毫秒级（`@Async`/`syncSend` 都不阻塞 HTTP 线程）。
   接口耗时本身差异不大——差异在下面的错误率。
2. **上传接口吞吐·按状态码** — 核心图。MQ 关：约 `50+4` 个任务在途后 500 飙升（拒单）；
   MQ 开：全程 200。这就是「MQ 把削峰失败从用户错误变成内部积压」的直接证据。
3. **任务端到端耗时分位数** — MQ 开的代价在这里：不拒单意味着积压全部排队，
   P99 e2e 会远高于 MQ 关（后者"甩掉"了排不进队的请求）。削峰不是免费的，这张图量化代价。
4. **单次处理耗时 P95·按路径** — 验证公平性：两轮的 standalone 处理耗时应一致（≈mock delay），
   否则对比无效。
5. **线程池积压/活跃/拒绝** — MQ 关：`queued` 顶到 50 → `rejected/s` 出现；
   MQ 开：`queued` 同样会满，但溢出由 broker 重投递兜底，`rejected` 不打到用户。
6. **任务完成吞吐** — 两轮应一致（≈ 4 线程 / mock delay），直观说明 **MQ 不提升处理能力，只改变积压的位置与失败的语义**。

k6 侧输出同样保留：`checks` 失败率 = 拒单率；`http_req_duration` P95/P99 与面板 1 互相印证。

## 注意事项

- **MQ 重投递退避**：极端积压下 RocketMQ 重试间隔递增（10s→30s→…），16 次后进死信队列，
  任务会永远停在 QUEUED——这正是 P3 要做的 reaper/消费并发调优的实证输入。
- **数据清理**：每轮压测会产生数百条 `video_task` 记录与 `storage/uploads/` 下的小文件，
  对比完可清理（`DELETE FROM video_task WHERE owner='k6-loadtest'`；删除 uploads 目录下当日文件）。
- **公平性**：两轮必须同一 `APP_TRANSCRIPT_MOCK_DELAY_MS`、同一 k6 参数、同一数据库模式。
- 压测账号由 k6 `setup()` 自动注册（`k6-loadtest`），无需手工准备。

## 相关文件

- `loadtest/upload-load.js` — k6 脚本
- `observability/prometheus.yml` — 抓取配置（5s 间隔）
- `observability/grafana/` — 数据源 + 仪表盘自动预置
- 指标定义：`WorkflowMetrics`（`video.task.processing/e2e/skipped`）+ 自动绑定的
  `http.server.requests`、`executor.*`，公共标签 `mq` 见 `MetricsConfig`
