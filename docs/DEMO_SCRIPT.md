# 5-10 分钟项目演示脚本

目标：让面试官先看到完整业务，再看到 Redis、RocketMQ、MinIO 和可靠性设计如何解决真实问题。不要只展示代码目录。

## 演示前准备

最稳妥的顺序：先用轻量模式演示业务，再展示已经保存的真实中间件验证证据。需要现场验证完整链路时再运行 full-stack 脚本。

轻量模式：

```powershell
$env:APP_REDIS_ENABLED="false"
$env:APP_MQ_ENABLED="false"
$env:APP_TRANSCRIPT_ENABLED="false"
$env:APP_SUMMARY_ENABLED="false"
$env:SPRING_DOCKER_COMPOSE_ENABLED="false"
$env:MANAGEMENT_HEALTH_REDIS_ENABLED="false"
mvn spring-boot:run "-Dspring-boot.run.profiles=h2"
```

打开：

- 工作台：<http://localhost:8081>
- 健康检查：<http://localhost:8081/actuator/health>
- 项目首页：`README.md`
- 验证证据：`docs/VERIFICATION_MATRIX.md`

准备一个较小的 MP4。真实 AI API 未配置时，系统会使用 Mock 转写和摘要，适合稳定演示业务状态流。

## 推荐讲解流程

### 0:00-1:00 业务问题

页面打开后直接说：

> 这是一个多用户视频内容理解平台。用户上传视频后，系统异步完成音频提取、语音转写和 AI 摘要，并提供历史记录、播放、失败重试和结果导出。项目重点解决三个工程问题：大文件上传不稳定、耗时任务拖垮请求链路，以及多人使用时文件和任务必须严格隔离。

此时只指向页面上的上传区、当前任务和历史任务，不先讲中间件名词。

### 1:00-3:00 完整用户链路

1. 注册或登录。
2. 选择普通上传，提交一个小视频。
3. 观察任务从 `QUEUED` 进入转写、摘要和完成状态。
4. 在历史任务中切换任务，查看转写和摘要。
5. 点击“复制结果”和“下载 Markdown”。
6. 展示播放、删除；如果有 `FAILED` 任务，再展示重试。

讲解：

> 上传接口创建的是可追踪的 `VideoTask`，慢处理不占着 HTTP 请求等待。每条任务都绑定 owner，查询、播放令牌、重试和删除都会校验当前用户。结果不只停留在页面里，还可以直接复制或导出为 Markdown。

### 3:00-5:00 三种上传方式

在上传策略中依次指出：

- **普通上传**：实现简单，适合小文件和本地开发；失败通常需要重传整个文件。
- **Redis 并发分片**：记录上传会话、已完成分片和 merge 锁，支持断点续传、失败分片重试、MD5 校验和秒传。
- **MinIO 对象存储直传**：后端签发短期 PUT URL，文件正文从浏览器直达对象存储，减少应用服务器带宽、磁盘和连接压力。

必须主动说明：

> Redis 本身不会让上传天然变快。速度主要受并发分片数、分片大小和网络影响；Redis 首先解决可恢复性和一致性。MinIO 直传也不会加快转写，它优化的是上传和播放的流量路径。

如果 MinIO 已启动，可打开 Console，展示 `uploads/direct/` 对象；否则展示 `docs/P4_OBJECT_STORAGE.md` 的三段式验证流程。

### 5:00-7:00 MQ 削峰实测

打开页面“异步实验室”的本地/RocketMQ 对比；也可以展示 `README.md` 的 MQ A/B 表格或 `loadtest/results/RESULTS.md`。

短压测数据：

| 指标 | MQ 关 | MQ 开 |
| --- | ---: | ---: |
| checks | 1365 | 1399 |
| 请求成功率 | 10.25% | 100% |
| HTTP 失败率 | 89.61% | 0% |
| 上传接口 p95 | 22.04 ms | 14.44 ms |

讲解：

> MQ 关闭时，本地线程池饱和后请求会收到 503，但任务已落库并由 reaper 补偿；MQ 开启后，请求先进入 broker，消费者按能力处理。消费者并发增加可以提高吞吐，但那是更多 worker 的效果。公平 A/B 默认让两边都是 4 个 worker，避免把并发差异误说成 MQ 加速。

加分点：指出大压测里 MQ 模式端到端等待曾达到 22 分钟，说明“100% 接收”还必须配合队列深度告警、限流、扩容和用户等待预期。

### 7:00-9:00 可靠性与工程证据

按一次处理链路讲四个保护：

1. `claimForProcessing` 只允许 `QUEUED` 首次占位，抵御 MQ 重复投递。
2. 内容 MD5 + single-flight 锁保证同一内容只执行一次昂贵处理，结果 fan-out 给其他任务。
3. 异常统一落为 `FAILED`，用户可以手动重试。
4. stale-task reaper 扫描长时间卡住的任务并重新发布，处理 worker 宕机等场景。

然后展示 `VERIFICATION_MATRIX.md`，说明每项主张由测试、脚本、页面还是历史实测支撑。

面试官追问上线方案时再补充：项目保留 Docker Compose + Caddy 自动 HTTPS，应用与文件域名分离，中间件不直接暴露公网，并有 preflight/smoke 脚本。这是可选架构能力，不是已发生的生产运营。

### 9:00-10:00 诚实边界与收尾

> 当前已经完成代码测试、本地真实中间件链路和 MQ A/B 实测，但没有虚构公网用户量、SLA 或收入。下一步优先完善媒体生命周期、上传会话审计和孤儿文件清理；如果未来真实上线，还要补 Flyway、备份恢复演练和 CI/CD。

一句话收尾：

> 我不是把 Redis、MQ 和 MinIO 堆进项目，而是分别用它们解决上传可恢复、处理削峰和文件流量卸载，再用幂等、锁、补偿、指标和验证脚本把完整链路闭环。

## 现场追问速答

**为什么分片有时比普通上传慢？**

小文件会多出 MD5、init、多个 HTTP 请求和 merge 开销。分片的第一价值是大文件失败后只重传缺失部分；并行在高带宽、高时延环境下才可能明显提速。

**MQ 为什么没有提升处理吞吐？**

吞吐取决于消费者数量、CPU、FFmpeg 和外部 AI 限额。MQ 只提供缓冲和解耦。要增加吞吐，需要扩消费者，并同时处理幂等、数据库连接、API 限流和积压监控。

**为什么 MinIO 需要 internal/public 两个 endpoint？**

应用容器通过 Docker 内网访问 `minio:9000`，浏览器只能访问公网文件域名。预签名 URL 把 host 纳入签名，因此签名时必须使用浏览器真正访问的 public endpoint。

**如何防止用户访问别人的视频？**

任务查询、删除、重试和播放令牌都绑定当前认证用户；播放 token 还绑定 owner、taskId 和 purpose。只改 URL 中的 taskId 会被拒绝。

## 演示失败备用路径

- Docker 不可用：用 H2 轻量模式走完整用户链路，再展示保存的 A/B 数据和验证矩阵。
- AI API 不可用：关闭 transcript/summary 外部调用，使用 Mock 结果，明确这是链路演示而非模型质量评测。
- 8081 被占用：先用 `Get-NetTCPConnection -LocalPort 8081` 查占用，不要随意修改已提交配置。
- 登录状态异常：浏览器控制台执行 `localStorage.clear(); location.reload();`。
- 完整验证：`powershell -NoProfile -ExecutionPolicy Bypass -File scripts\verify-full-stack.ps1`。

每项能力的测试层级和通过标准见 `docs/VERIFICATION_MATRIX.md`。
