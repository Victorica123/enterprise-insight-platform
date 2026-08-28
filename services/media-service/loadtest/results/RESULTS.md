# P2 压测实测结果快照（2026-07-02）

> 2026-07-18 说明：以下是历史原始结果，不回写当时数据。短复验的 MQ consumer 当时使用框架默认 20 线程，
> 所以请求接收率差异有效，但完成数量不能直接归因给 MQ。当前代码显式配置 4 个 MQ consumer 线程，
> 与本地 executor max=4 对齐；新页面同参数结果见 `docs/ASYNC_LAB.md`。

配置：mock 延迟 3s、10 VU、10s 爬坡 + 100s 稳态、THINK 0.5s、单文件 64KB。
两轮同参数，唯一变量 `app.mq.enabled`。线程池 core2/max4/queue50。

## 头条

| 指标 | MQ 关 | MQ 开 |
|---|---|---|
| 上传总数 | 2211 | 2211 |
| 成功率 | 9.5% (210) | 100% (2211) |
| 拒单 HTTP 500 | 2001 (90.5%) | 0 |
| 成功请求延迟 P50/P99 | 10ms / 10ms | 10ms / 10ms |
| 线程池 queued 峰值 | 50 | 50 |
| 窗口内完成任务 | ~157 | ~159 |
| processing P95 | 3.2s | 3.2s |
| e2e (直方图, 30s 封顶) | ≥30s 饱和 | ≥30s 饱和 |
| e2e 真实值 (DB) | 已清库 (队列有界, ~≤40s) | avg 567.6s, min 3.7s, max 1353.8s |

## 结论

同 13× 过载：MQ 把"用户可见失败"换成"内部积压延迟"。
- 本地 @Async：90% 拒单，但 e2e 有界（≤40s）——快速失败、延迟可控。
- RocketMQ：0 拒单，但 e2e 冲到 22 分钟——照单全收、延迟无界。
- 吞吐相同（~1.3/s）：MQ 是削峰/解耦，不是加速。

时间窗：见 windows.txt。原始 k6 输出：k6-mqoff.txt / k6-mqon.txt。

## 已知测量局限（已修，下轮生效）

Micrometer Timer 直方图默认封顶 30s → 两轮 e2e P99 都被钳在 30s。
已在 application.yml 加 `management.metrics.distribution.maximum-expected-value.video.task.e2e=600s`，
后续跑法可在 Grafana 直接看真实 e2e 分位，无需回退到 DB 计算。

## 短压测复验（2026-07-03）

目的：在修复 RocketMQ consumer 背压路径后，用更短参数复验 MQ 开/关差异仍成立。

配置：真实 Docker Redis + MySQL + RocketMQ，mock 延迟 2s，8 VU，8s 爬坡 + 25s 稳态，THINK 0.2s，单文件 16KB。

| 指标 | MQ 关 | MQ 开 |
|---|---|---|
| k6 checks | 1365 | 1399 |
| 成功率 | 10.25% (140) | 100% (1399) |
| HTTP 失败率 | 89.61% | 0% |
| 上传接口 p95 | 22.04ms | 14.44ms |
| 数据库任务状态 | COMPLETED 120 / QUEUED 1241 / TRANSCRIBING 4 | COMPLETED 624 / QUEUED 755 / TRANSCRIBING 20 |
| 已完成任务 e2e | avg 21.0s / max 28s | avg 22.0s / max 45s |

复验结论：MQ 开启后上传接口可以快速返回“平台已接收”，但后台任务仍按消费者能力慢慢处理。MQ 没有提升单个任务处理速度；它把高峰期的 HTTP 500 拒单转成了内部队列积压。

原始输出：`k6-short-mqoff.txt` / `k6-short-mqon.txt`。
