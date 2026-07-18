# 视频内容理解平台：面试知识点

> 截至 2026-07-18。只讲已经实现或实际验证的内容；规划必须明确说是下一步。

## 1. 项目定位

这是一个多用户视频内容理解平台。用户通过普通上传、Redis 分片上传或 MinIO 直传提交视频，系统创建异步任务，经 FFmpeg、Whisper 兼容接口和 LLM 兼容接口生成转写与摘要，并提供状态、播放、重试、删除和 Markdown 导出。

后端面试的主线不是“用了多少中间件”，而是：

1. 大文件失败后如何避免整文件重传；
2. 慢任务和流量高峰如何不拖垮 HTTP 请求；
3. MQ 重投、并发重复提交和 worker 宕机时如何保证状态可恢复；
4. 多用户环境如何隔离任务与文件；
5. 如何用测试、指标和脚本证明这些能力。

## 2. 架构链路

```text
浏览器
  -> JWT 鉴权
  -> 普通上传 / Redis 分片 / MinIO 预签名直传
  -> 创建 VideoTask(QUEUED)
  -> 本地 @Async 或 RocketMQ 发布 taskId
  -> claimForProcessing 幂等占位
  -> FFmpeg -> Whisper -> LLM
  -> COMPLETED / FAILED
  -> 查询、播放、复制、Markdown 导出、重试、删除
```

慢外部 I/O 不包在长数据库事务中。任务状态通过 `VideoTaskService` 的短事务分阶段推进，避免长期占用连接和扩大回滚范围。

## 3. Redis 分片上传

### 解决什么

- Redis 保存 upload session、已上传 chunk 集合和 TTL；
- `status` 返回已完成分片，前端只补传缺失部分；
- merge 使用分布式锁，防止重复点击产生重复副作用；
- 合并后重新计算整文件 MD5，不匹配则返回 400、清理半成品且不创建任务；
- MD5 命中已处理内容时可秒传并复用结果。

### 为什么可能更慢

小文件会增加 MD5、init、多个请求和 merge 开销。Redis 不负责传输文件正文，因此不能宣称“用了 Redis 就更快”。大文件场景的核心收益是失败恢复；并行 chunk 只有在网络和服务端允许时才可能缩短传输时间。

### 高频追问

**为什么使用 MD5？**

用于内容指纹、意外损坏校验和去重，不用于密码或安全签名。安全敏感场景可以换 SHA-256；大规模去重可叠加文件大小和二次校验降低碰撞风险。

**merge 为什么要锁？**

merge 会写文件、清 Redis 会话、创建任务并发布消息，是有副作用的临界区。锁避免重试或双击并发执行。接口还应尽量返回已有结果，不能只依赖锁掩盖幂等问题。

## 4. RocketMQ 削峰

### 正确结论

RocketMQ 不改变单个视频的处理成本，也不会凭空增加 worker 吞吐。它把高峰期线程池拒绝造成的 HTTP 失败，转换成 broker 中可恢复、可观测的排队。增加 consumer 数可以提升吞吐，但原因是 worker 增加，而不是消息经过 MQ 后计算更快。

短压测使用真实 Redis、MySQL、RocketMQ，5 VU、2 秒 Mock 延迟：

| 指标 | MQ 关 | MQ 开 |
| --- | ---: | ---: |
| checks | 1365 | 1399 |
| 请求成功率 | 10.25% | 100% |
| HTTP 失败率 | 89.61% | 0% |
| 上传 p95 | 22.04 ms | 14.44 ms |

历史长压测中，两种模式处理吞吐都约为 1.3/s；MQ 开启后积压任务的真实端到端等待最高约 1354 秒。这证明“请求接住了”不等于“处理变快了”。历史短复验曾使用 MQ 默认 20 消费线程，因此其完成数不能与本地 4 线程直接比较；当前已显式配置 `APP_MQ_CONSUMER_THREADS=4` 作为公平 A/B 默认值。

页面异步实验室的同参数本地实测：80 个任务、500 ms Mock、4 worker。本地模式接收 54、拒绝 26，依靠 10 秒 reaper 最终 80 个完成，约 18.55 秒；RocketMQ 接收 80、拒绝 0，80 个完成约 11.32 秒。差异来自削峰和省掉拒绝后的补偿等待，不是单任务变快。

### 高并发下必须一起考虑

- **幂等**：MQ 至少一次投递可能重复，`claimForProcessing` 只让首次状态迁移成功者继续。
- **背压**：监控 queue depth、最老消息年龄、消费者速率；超过阈值要限流、降级或扩容。
- **连接池**：增加消费者前确认数据库连接池和外部 API 配额，否则只是把瓶颈后移。
- **热点与重复内容**：内容 MD5 single-flight 让并发相同视频只处理一次。
- **毒消息**：重试次数必须有上限，最终落失败状态或死信队列，不能无限循环。
- **用户预期**：接口返回“已接收”后要展示 QUEUED 和处理状态，不能误报“已完成”。
- **准入控制**：按用户限制活跃任务数，容量满返回 429；数据库用户行悲观锁防止并发请求同时绕过配额。

## 5. MinIO/S3 对象存储

### 三段式直传

1. `direct/init` 校验文件元数据，签发短期 PUT URL 和 upload token；
2. 浏览器直接 PUT 到 MinIO，视频正文不经过应用服务器；
3. `direct/complete` 校验 token、owner、storagePath 和对象存在性，再创建任务。

重复 complete 会返回同一 owner/storagePath 的已有任务，避免刷新或网络重试重复发布工作流。

### 价值与边界

- 降低应用服务器带宽、磁盘和连接压力；
- 多应用实例共享同一份媒体；
- 播放通过短时预签名 URL 让对象存储承担 Range 流量；
- 不会加快 FFmpeg、转写或摘要。

### internal/public endpoint

应用容器访问 `http://minio:9000`，浏览器访问 `https://files.example.com`。S3 签名包含 host，所以预签名必须使用浏览器真实可达的 public endpoint；后端内部读写仍使用 internal endpoint。

## 6. 一致性、幂等与恢复

### 三层防护

- **任务幂等**：状态机 claim 防止同一 taskId 被重复处理；
- **内容 single-flight**：按 MD5 获取 Redisson 看门狗锁，只有赢家执行昂贵处理；
- **结果 fan-out**：赢家完成后，把结果复用给所有等待的同内容任务。

长处理使用看门狗自动续租，避免固定 TTL 在任务未结束时过期。merge 属于秒级操作，可使用有限租期锁。

### 失败恢复

- 处理异常统一落库为 `FAILED`，保留截断后的错误原因；
- owner 可以手动重试自己的失败任务；
- stale-task reaper 扫描超时 `QUEUED/TRANSCRIBING/SUMMARIZING` 任务，重置并重新发布；
- 自动补偿和手动重试记录 `video.task.requeued{source=reaper|manual}`。

reaper 提供的是最终恢复能力，不保证 exactly-once。副作用仍必须幂等，阈值也必须高于正常任务耗时，避免误判慢任务。

## 7. 安全与多用户隔离

- JWT 只解决身份认证，资源接口仍必须按 owner 查询；
- 上传会话、任务详情、删除、重试和播放 token 都绑定当前用户；
- 播放 token 绑定 owner、taskId、purpose 和过期时间；
- 合法 token 换到另一个 taskId 会返回 403；
- 文件名经过安全化，防止路径穿越；
- MySQL、Redis、RocketMQ、Prometheus、Grafana 不直接暴露公网。

面试时可以强调：水平越权通常不是“没有登录”，而是“登录用户访问了不属于自己的资源”，所以必须有两个账号的越权测试。

## 8. 可观测与排障

证据分四层：

- 单元测试验证算法与服务边界；
- Web/Security 测试验证 HTTP 与 owner 隔离；
- Docker runtime 脚本验证真实 Redis、MySQL、RocketMQ、MinIO；
- 页面人工验证完整用户体验。

排障按边界进行：

1. `/actuator/health` 判断应用是否启动；
2. app 日志判断鉴权、参数和工作流异常；
3. MinIO 日志/CORS 判断直传 PUT；
4. RocketMQ 日志与队列状态判断消息积压；
5. MySQL 任务状态判断是否持久化；
6. Redis keys 判断上传会话是否合并后清理。

`scripts/verify-full-stack.ps1` 验证本地真实中间件链路；页面“异步实验室”提供可观察 A/B。可选部署脚本只在讨论公网架构时使用。

## 9. 本地可复现的工程证据

面试现场不依赖公网服务器，也能展示：

- 79 个不依赖外部中间件的自动化测试；
- `verify-full-stack.ps1` 的 Redis、MySQL、RocketMQ 真实链路；
- MinIO 预签名直传、完成回调和播放；
- 页面异步实验室的本地/MQ 同参数 A/B；
- owner 越权、MD5 错误、重复消息、任务饱和和补偿等故障情景。

证据必须同时说明环境和边界。Mock AI 证明状态机和队列行为，不代表真实模型质量或吞吐。

### 可选部署扩展

项目选择单服务器 Docker Compose + Caddy，而不是直接上 Kubernetes：

- Caddy 自动 HTTPS，应用域名和文件域名分离；
- MySQL、Redis、RocketMQ 只在 Compose 网络内；
- Prometheus/Grafana 绑定 localhost，通过 SSH tunnel 查看；
- secrets 和 endpoint 通过 `.env` 外部化；
- 容器日志轮转、健康检查、preflight 和 smoke 流程已提供。

这个方案适合以后低成本试用或回答架构追问，不是当前演示的前置条件，也不应宣称具备大规模生产 SLA。

## 10. 用户可见功能如何体现工程价值

- 三种上传策略和上传耗时观测，让用户直接比较可靠性与链路差异；
- 历史记录保留每次上传方式，不会因当前切换策略而被改写；
- 失败任务有明确状态和重试入口；
- 转写与摘要可复制、下载 Markdown，不只是后台数据库里的结果；
- 播放、删除和任务切换都遵守 owner 隔离。

## 11. 已知边界

已实现并验证：79 个自动化测试、真实 Redis/MySQL/RocketMQ 链路、MinIO 直传与播放、页面异步 A/B、重试/reaper、任务配额、Compose/Caddy/preflight。

仍需继续完善：

- Hibernate `ddl-auto=update` 应替换为 Flyway/Liquibase；
- 轻量 S3 Signature V4 实现可替换为官方 SDK；
- 独立 upload-session 表，用于审计、过期和孤儿对象清理；
- 用户/IP 限流、并发配额、容量配额和文件安全扫描；
- 数据库与对象存储备份恢复演练；
- CI/CD、灰度和回滚自动化；
- 真实公网流量、容量基线和 SLA。

## 12. 一分钟回答模板

> 我做的是一个多用户视频内容理解平台，重点不是 CRUD，而是大文件上传和异步 AI 工作流。上传侧有普通上传、Redis 分片断点续传和 MinIO 预签名直传；处理侧用本地异步或 RocketMQ 解耦，通过状态机 claim、内容级 single-flight、失败重试、用户任务配额和 stale-task reaper 保证可恢复。页面同参数 A/B 中，本地线程池只接收 54/80，RocketMQ 接收 80/80；两边都是 4 个 worker，单任务成本不变，差异来自削峰和补偿等待。项目有 79 个自动化测试和真实中间件 smoke，不依赖公网服务器也能完整复现。
