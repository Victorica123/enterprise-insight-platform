# 压测指南：MQ 开/关量化对比（P2）

> 目标：用同一负载压两轮 —— `app.mq.enabled=false`（本地 `@Async`）vs `=true`（RocketMQ）——
> 用 P50/P99、错误率、吞吐、积压曲线量化「MQ 异步削峰」到底带来了什么、代价是什么。

## 原理：对比的到底是什么

公平 A/B 时两种模式必须使用相同 worker 并发和相同转写耗时。当前配置默认让 RocketMQ
`consumer-threads=4` 对齐本地 `videoTaskExecutor maxPoolSize=4`，差别集中在**提交请求后、开始处理前**这一段：

| | MQ 关（本地 @Async） | MQ 开（RocketMQ） |
|---|---|---|
| 上传接口做什么 | `publish()` 直接把任务投进线程池 | `syncSend` 毫秒级投给 broker |
| 积压放在哪 | JVM 内队列（上限 50） | broker（磁盘，几乎无上限） |
| 超限会怎样 | `TaskRejectedException` → 用户收到 **503**，任务等待补偿 | 消费端拒收 → broker **重投递**，用户无感 |
| 代价 | 高峰期直接拒单 | 端到端延迟拉长（排队转移到 broker） |

> 关键前提：Mock 转写默认**瞬间返回**，线程池永不饱和，两种模式测不出差异。
> 压测必须设 `APP_TRANSCRIPT_MOCK_DELAY_MS`（如 5000 = 5s/任务）还原真实转写的
> 慢消费者特征，**两轮用同一值**保证公平。

> 2026-07-18 起，本地线程池饱和由通用 500 改为明确的 503；任务已经落库，stale-task reaper
> 会补偿重新投递。历史结果文件仍保留当时实际观察到的 500，不回写历史数据。短复验曾使用
> RocketMQ 默认 20 个消费线程，因此其“完成数量”不能与本地 4 线程直接归因给 MQ；接收率差异仍然有效。

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
$env:APP_TRANSCRIPT_MOCK_DELAY_MS="5000"; $env:APP_MAX_ACTIVE_TASKS_PER_USER="0"; mvn spring-boot:run
```

```bash
# 另一个终端
k6 run loadtest/upload-load.js
```

跑完停掉应用（Ctrl+C）。

### 2）轮 2：MQ 开

```powershell
docker compose --profile mq up -d        # RocketMQ namesrv + broker
$env:APP_TRANSCRIPT_MOCK_DELAY_MS="5000"; $env:APP_MAX_ACTIVE_TASKS_PER_USER="0"; $env:APP_MQ_ENABLED="true"; $env:APP_MQ_CONSUMER_THREADS="4"; mvn spring-boot:run
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
2. **上传接口吞吐·按状态码** — 核心图。MQ 关：约 `50+4` 个任务在途后 503 飙升（拒单）；
   MQ 开：全程 200。这就是「MQ 把削峰失败从用户错误变成内部积压」的直接证据。
3. **任务端到端耗时分位数** — MQ 开的代价在这里：不拒单意味着积压全部排队，
   P99 e2e 会远高于 MQ 关（后者"甩掉"了排不进队的请求）。削峰不是免费的，这张图量化代价。
4. **单次处理耗时 P95·按路径** — 验证公平性：两轮的 standalone 处理耗时应一致（≈mock delay），
   否则对比无效。
5. **线程池积压/活跃/拒绝** — MQ 关：`queued` 顶到 50 → `rejected/s` 出现；
   MQ 开：`queued` 同样会满，但溢出由 broker 重投递兜底，`rejected` 不打到用户。
6. **任务完成吞吐** — 两轮应一致（≈ 4 线程 / mock delay），直观说明 **MQ 不提升处理能力，只改变积压的位置与失败的语义**。

k6 侧输出同样保留：`checks` 失败率 = 拒单率；`http_req_duration` P95/P99 与面板 1 互相印证。

## 历史实测结果（2026-07-02，旧版错误码）

**配置**：mock 延迟 3s/任务、10 VU、10s 爬坡 + 100s 稳态、THINK 0.5s、单文件 64KB。
两轮同参数,唯一变量 `app.mq.enabled`。线程池 core2/max4/queue50 → 处理能力上限 ≈ 4/3s ≈ **1.33 任务/s**;而到达率 ≈ 17/s,是 ~13× 过载,刻意压满以暴露差异。

### 头条:同样过载,失败率天差地别

| 指标 | MQ 关（本地 @Async） | MQ 开（RocketMQ） |
|---|---|---|
| 上传总数(k6) | 2211 | 2211 |
| **成功率** | **9.5%**（210） | **100%**（2211） |
| **拒单(HTTP 500)** | **2001（90.5%）** | **0** |
| 成功请求延迟 P50/P99 | 10ms / 10ms | 10ms / 10ms |

MQ 关:线程池 + 队列(50)打满后,`publish()` 提交被 `TaskRejectedException` 拒绝,直接抛到 HTTP 线程 → 用户收到 500。90% 的上传当场失败。
MQ 开:`syncSend` 把任务丢给 broker(毫秒级),全部 200,用户无感。

### 关键:MQ 不提升处理能力,只搬运积压

| 服务端指标(Prometheus, 压测窗口) | MQ 关 | MQ 开 |
|---|---|---|
| 线程池 queued 峰值 | 50（打满） | 50（打满） |
| 窗口内完成任务数 | ~157 | ~159 |
| 纯处理耗时 processing P95 | 3.2s | 3.2s |

两轮**吞吐和单任务耗时完全一致**——4 线程 × (1/3s) ≈ 1.33/s。MQ 没让处理变快一分,它只是把"超出处理能力的部分"从`线程池队列(满了就拒)`搬到了`broker(持久缓冲)`。

### 代价:e2e 端到端延迟爆炸

端到端耗时(入队→完成)才是 MQ 削峰的账单。Micrometer Timer 默认直方图封顶 30s,两轮 P99 都被钳在 30s(已在本次后把 `maximum-expected-value` 抬到 600s,后续跑法可见真实分位)。绕开直方图、直接从数据库算 MQ 开这轮的真实 e2e:

```
completed=1547  avg=567.6s  min=3.7s  max=1353.8s   （另有 944 个仍在排队,以 ~1.3/s 缓慢消化）
```

- MQ 关:拒单把在途任务钉在队列上限(50),被接受的任务 e2e 有界(~30-40s),**快速失败、延迟可控**。
- MQ 开:0 拒单,但持续过载下积压堆到 broker,任务 e2e 从 3.7s 一路拉到 **22 分钟**,平均近 10 分钟,**照单全收、延迟无界**。

### 一句话结论(面试可直接讲)

> 同样的 13× 过载下,**MQ 把"用户可见的失败"换成了"内部积压的延迟"**:本地 @Async 快速拒单(90% 失败但 e2e≤40s),RocketMQ 全部接住(0 失败但 e2e 冲到分钟级)。两者处理吞吐相同(~1.3/s)——**MQ 是削峰/解耦,不是加速**。选哪种取决于业务:能容忍延迟不能容忍丢请求(如转码任务)→ 上 MQ;要求实时响应宁可拒绝(如同步查询)→ 快速失败更好。真正要提吞吐得靠 P3 调线程池/消费并发。

> 原始输出:`loadtest/results/k6-mqoff.txt`、`k6-mqon.txt`、`windows.txt`(压测时间窗)。

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
