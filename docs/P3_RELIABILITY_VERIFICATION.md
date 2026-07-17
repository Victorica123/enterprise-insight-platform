# P3 可靠性验证：任务卡住后的自动补偿

## 这轮解决什么

P2 压测证明：RocketMQ 能把高峰请求接住，但代价是后台排队变长。真实系统还会遇到更麻烦的问题：worker 处理中宕机、MQ 重投递、单飞赢家消失、任务长期停在 `TRANSCRIBING`。

P3 本轮补的是“异步任务补偿机制”：

- 定时扫描长期停在 `QUEUED` / `TRANSCRIBING` / `SUMMARIZING` 的任务。
- 把它们重置回 `QUEUED`。
- 重新走现有 `WorkflowPublisher`，兼容本地 `@Async` 和 RocketMQ。
- 入口仍靠 `claimForProcessing()` 做幂等，避免重复处理同一个任务。

后续又补了一条用户可见的恢复路径：

- `POST /api/workflow/tasks/{taskId}/retry` 允许当前登录用户手动重试自己的 `FAILED` 任务。
- 重试会清空旧错误信息，把任务放回 `QUEUED`，再走同一个 `WorkflowPublisher`。
- 自动补偿和手动重试都会记录 `video.task.requeued` 指标，`source=reaper|manual`。
- 前端历史任务里，失败任务会出现“重试”按钮。

## 你可以怎么验证

### 快速验证（不启动服务）

```powershell
mvn test "-Dtest=VideoTaskServiceTests,StaleWorkflowTaskReaperTests,WorkflowProcessorTests"
```

预期：

- `VideoTaskServiceTests` 证明超时任务会被重置成 `QUEUED`。
- `StaleWorkflowTaskReaperTests` 证明 reaper 会重新 publish 返回的 taskId。
- `WorkflowProcessorTests` 证明重复投递不会重复执行已被抢占/已完成任务。

### 前端可视化验证

启动服务后打开 `http://localhost:8081`：

1. 注册或登录。
2. 上传视频，观察上传观测、当前任务、历史任务。
3. 如果任务失败，历史任务会显示“重试”按钮；点击后任务重新进入排队。
4. 右侧“工程验证”面板用通俗语言解释 MQ 削峰、P3 补偿、P4 对象存储和失败重试。

### 手动验证思路（启动服务后）

为了方便观察，把阈值调小：

```powershell
$env:APP_WORKFLOW_STALE_TASK_TIMEOUT="10s"
$env:APP_WORKFLOW_REAPER_INTERVAL_MS="5000"
$env:APP_WORKFLOW_REAPER_INITIAL_DELAY_MS="5000"
```

然后启动服务、制造一个卡住任务：

1. 上传一个视频，拿到 `taskId`。
2. 在数据库里把该任务状态手动改成 `TRANSCRIBING`，并把 `updated_at` 改到 10 秒以前。
3. 等 5-10 秒，看日志出现 `Requeueing ... stale workflow task(s)`。
4. 再查任务状态，应回到 `QUEUED` 并重新被发布处理。

SQL 示例按实际表字段大小写调整：

```sql
UPDATE video_task
SET status='TRANSCRIBING', updated_at=DATE_SUB(NOW(), INTERVAL 2 MINUTE)
WHERE task_id='你的 taskId';
```

## 结果怎么讲

通俗版：

> MQ 能接住高峰，但后台 worker 可能处理到一半挂掉。P3 做的是任务补偿：发现任务长时间卡在处理中，就把它重新放回队列。因为处理入口有状态抢占，所以重投递是安全的。

面试版：

> 我没有把 MQ 当成银弹。异步任务系统要同时考虑削峰、幂等、补偿和可观测。这里用 `claimForProcessing()` 保证重复消息幂等，用 `StaleWorkflowTaskReaper` 扫描非终态超时任务并重投递，避免任务永久卡死。

## 高并发下常见工程问题与解法

| 问题 | 现象 | 可行解法 | 本项目对应点 |
|---|---|---|---|
| 线程池打满 | 上传接口 500 或任务排队暴涨 | MQ 缓冲、限流、线程池隔离 | P2 压测证明 MQ 把拒单变成排队 |
| 重复消息 | 同一个任务被处理多次 | 状态抢占/幂等键 | `claimForProcessing()` |
| worker 宕机 | 任务长期 `TRANSCRIBING` | 定时 reaper 重投递 | `StaleWorkflowTaskReaper` |
| 分布式锁过期 | 同内容被重复处理 | Redisson watchdog 单飞锁 | `tryLockWithWatchdog` |
| 队列无限积压 | 用户等很久 | 排队时间指标、限流、扩容消费者 | `video.task.e2e` + P2 结果 |
| 文件存储瓶颈 | 本地磁盘满、下载占满应用带宽 | 对象存储 + 预签名 URL | P4 对象存储准备 |

## 当前验证结果

- `node --check src/main/resources/static/app.js` 通过。
- 聚焦测试：`WorkflowControllerTests,VideoTaskServiceTests,StaleWorkflowTaskReaperTests`，`13 tests, 0 failures, 0 errors`。
- 全量测试：`mvn test`，`60 tests, 0 failures, 0 errors`。
