# 本地异步实验室

不需要公网服务器。这个实验在一台电脑上使用真实 Spring Boot 线程池和 Docker RocketMQ，页面只负责发请求和读取任务状态，不模拟后端结果。

## 实验解决什么疑问

- 上传接口为什么可以先返回“已接收”，后台再慢慢处理；
- 本地 `@Async` 队列满时为什么会拒绝请求；
- RocketMQ 如何把 HTTP 拒绝转换成 broker 积压；
- 被拒绝但已经落库的任务如何由 stale-task reaper 自动补偿；
- MQ 和消费者并发分别对接收率、排队和处理吞吐产生什么影响。

## 第一次：本地线程池

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File scripts\start-async-lab.ps1 -Mode local
```

1. 打开 <http://localhost:8081>，注册或登录。
2. 找到右侧“异步实验室”。
3. 保持任务数 `80`，点击“发送任务”。
4. 观察 HTTP 接收、HTTP 拒绝、后台任务和完成数。
5. 完成后点击“清理本轮任务”。
6. 回到终端按 `Ctrl+C` 停止应用。

默认参数：Mock 处理延迟 2 秒、关闭单用户配额、本地线程池 `core=2/max=4/queue=50`。因此 80 个并发请求可以稳定暴露线程池容量边界。

## 第二次：RocketMQ

先启动 Docker Desktop，再运行：

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File scripts\start-async-lab.ps1 -Mode mq
```

脚本会启动真实 RocketMQ nameserver/broker，再以 H2 + Mock AI 运行应用。H2 重启后账号会清空，所以页面上重新点一次“注册”。继续发送相同数量任务。

浏览器会把最近一次本地模式和 RocketMQ 模式结果保存在 `localStorage`，应用重启后仍可并排查看。

## 如何解释结果

本地模式：

- 线程池满后返回 503，而不是把请求无限堆在 JVM 内存；
- `VideoTask` 在 publish 前已经落库，因此页面能看到后台任务数大于 HTTP 接收数；
- 实验脚本把 stale timeout 调到 10 秒，补偿器会重新投递这些任务并最终完成。

RocketMQ 模式：

- HTTP 请求只负责创建任务并把 taskId 发到 broker，通常能全部接收；
- 积压从 JVM 有界队列移动到 RocketMQ；
- 单个任务不会因为“经过 MQ”而变快；吞吐提升来自增加消费者并发，MQ 本身提供缓冲、解耦和重试边界；
- 项目默认把 MQ 消费线程设为 4，与本地线程池 max=4 对齐，避免把 worker 数量差异误说成 MQ 加速。

## 本轮真实 A/B 结果

参数：16 KB 模拟视频、Mock 500 ms、配额关闭。

- 本地 `@Async`：80 个请求，HTTP 接收 54、拒绝 26；后台 80 个任务经补偿全部完成，约 18.55 秒。
- RocketMQ：80 个请求，HTTP 接收 80、拒绝 0；80 个任务全部完成，约 11.32 秒。

两轮都是 4 个 worker、16 KB 文件和 500 ms Mock。RocketMQ 没有改变单任务的 500 ms 处理时间；总耗时更短主要因为本地模式有 26 个任务需要等待 10 秒 reaper 补偿。这个实验验证接收率、积压位置和恢复过程，不代表公网容量。完整压测方法见 `docs/LOADTEST.md`。

## 常见问题

- 提示 Docker 未运行：启动 Docker Desktop，再运行 `-Mode mq`。
- 8081 被占用：先停止旧的 Maven 进程，不要同时启动两种模式。
- Mock 0 ms 看不出排队：使用脚本默认的 2000 ms，或传 `-MockDelayMs 5000`。
- 配额导致 429：实验脚本自动设置 `APP_MAX_ACTIVE_TASKS_PER_USER=0`；正常小规模运行默认保留配额保护。
