# 功能验证矩阵

这份文档回答一个问题：项目中的每项能力如何被证明，而不是只存在于代码或简历描述里。

验证分为四层：

- **U（Unit）**：纯单元测试，验证算法和服务边界。
- **W（Web）**：MockMvc / Spring Security，验证 HTTP、JWT 和 owner 隔离。
- **R（Runtime）**：真实 Docker 中间件或端到端脚本。
- **M（Manual）**：用户可以在页面直接观察和参与验证。

## 核心业务

| 能力 | 层级 | 自动验证 | 页面/人工验证 | 通过标准 |
| --- | --- | --- | --- | --- |
| 注册、登录、JWT | W | `JwtSecurityIntegrationTests` | 注册后刷新页面仍能恢复登录 | 合法 token 成功，缺失/非法 token 被拒绝 |
| owner 数据隔离 | W/U | `WorkflowControllerTests`、`MediaControllerTests` | 两个账号互相查询任务 | 只能访问自己的上传、任务和播放令牌 |
| 普通上传 | W/R/M | `MediaControllerTests`、`smoke-test.ps1` | 选择“普通上传” | 返回 taskId，任务进入状态机 |
| 任务查询与历史 | W/M | `WorkflowControllerTests` | “我的视频”选择历史任务 | owner 过滤、详情可加载 |
| 结果查看 | U/M | `WorkflowProcessorTests` | 转写/摘要页签 | 完成任务展示 transcript/summary |
| 结果交付 | M | 前端 JS 语法检查 | “复制结果”“Markdown” | 复制完整内容并下载合法文件名 |
| 任务删除 | W/M | `WorkflowControllerTests` | 历史记录删除 | owner 校验，删除后列表消失 |
| 失败重试 | U/W/M | `VideoTaskServiceTests`、`WorkflowControllerTests` | FAILED 任务点击重试 | 仅 owner 可重试，状态回到 QUEUED |
| 单用户任务配额 | U/W/M | `VideoTaskServiceTests`、`VideoTaskQuotaIntegrationTests`、`MediaControllerTests` | 页面“处理中 x/y” | 10 并发、上限 3 时恰好只创建 3 个；满额返回 429 |

## 大文件上传

| 能力 | 层级 | 自动验证 | 页面/人工验证 | 通过标准 |
| --- | --- | --- | --- | --- |
| 分片 init/chunk/merge | U/W/R/M | `ChunkUploadServiceTests`、`verify-full-stack.ps1` | “Redis 并发分片” | 分片记录完整并按序合并 |
| 断点状态 | U/R/M | `ChunkUploadServiceTests`、full-stack status 检查 | 中断后重新选择同一文件 | 已上传 chunk 被跳过 |
| 分片边界 | U/W | `ChunkUploadServiceTests`、`MediaControllerTests` | 非法 index | 返回明确 4xx，不写越界分片 |
| 合并互斥 | U | `ChunkUploadServiceTests` | 并发 merge 场景 | 只有一个请求进入副作用路径 |
| MD5 完整性 | U/R | `ChunkUploadServiceTests` | 声明错误 MD5 | 返回 400，半成品清理，不建任务 |
| 秒传 | U/M | `ChunkUploadServiceTests` | 重复上传相同内容 | init 返回 exists，跳过重复传输 |
| 上传观测 | M | 前端 JS 语法检查 | 三种模式依次上传 | 历史结果不随模式切换被改写 |

## 对象存储与播放

| 能力 | 层级 | 自动验证 | 页面/人工验证 | 通过标准 |
| --- | --- | --- | --- | --- |
| MinIO/S3 保存 | U/R | `S3MediaStorageServiceTests`、`verify-deploy.ps1` | 对象存储直传 | bucket 中存在对象 |
| 浏览器直传 | U/W/R/M | `DirectUploadServiceTests`、deploy smoke | init → PUT → complete | complete 幂等，只发布一次任务 |
| 内外 endpoint | U | `S3MediaStorageServiceTests` | 公网 files 域名 | 浏览器 URL 使用 public endpoint，后端走内网 |
| 播放令牌 | W | `VideoPlaybackControllerTests` | 完成任务出现播放器 | token 绑定 taskId/owner/purpose |
| HTTP Range | W/R/M | `VideoPlaybackControllerTests` | 拖动视频进度条 | Range 返回 206 和正确 Content-Range |
| S3 播放重定向 | W/U | 播放与存储测试 | MinIO 模式播放 | 返回短时效预签名 URL |

## 异步工作流与可靠性

| 能力 | 层级 | 自动验证 | 运行时验证 | 通过标准 |
| --- | --- | --- | --- | --- |
| 本地异步发布 | U | `WorkflowProcessorTests` | H2 轻量模式 | HTTP 快速返回，后台推进状态 |
| RocketMQ 发布/消费 | U/R | `RocketMqWorkflowConsumerTests`、full-stack | 真实 namesrv/broker | 消息最终完成任务 |
| MQ 削峰 | R | k6 A/B + Prometheus/Grafana | 同参数开关 MQ | MQ 开：请求成功率 100%；MQ 关：线程池拒绝 |
| 页面异步实验室 | R/M | `start-async-lab.ps1` | 80 个任务切换 local/mq | 真实任务状态与 HTTP 接收/拒绝并排显示 |
| 本地过载语义 | W/R | `MediaControllerTests`、异步实验室 | 本地线程池压满 | 返回 503 单行警告，任务由 reaper 补偿 |
| 幂等 claim | U | `WorkflowProcessorTests`、`VideoTaskServiceTests` | 重复消息 | 仅 QUEUED 的首次 claim 继续 |
| 内容级 single-flight | U | `WorkflowProcessorTests` | 同 MD5 并发任务 | 赢家处理，其他任务 fan-out 复用 |
| 看门狗锁 | U/设计 | 锁接口与工作流测试 | 长处理场景 | 长任务锁自动续期，避免重复处理 |
| 失败落库 | U | `WorkflowProcessorTests` | Mock 服务抛错 | 状态为 FAILED，错误信息截断 |
| stale task 补偿 | U | `StaleWorkflowTaskReaperTests` | 调短 timeout | 超时非终态重置并重新发布 |
| 临时文件清理 | U | 工作流/上传测试 | 人工制造失败 | FFmpeg/merge 异常不残留半成品 |

## 部署与可观测性

| 能力 | 层级 | 验证命令 | 通过标准 |
| --- | --- | --- | --- |
| 单元测试自洽 | U/W | `mvn test` | 79 tests，0 failures |
| 前端语法 | U | `node --check src/main/resources/static/app.js` | 退出码 0 |
| Compose 解析 | R | `docker compose --env-file .env.example -f docker-compose.prod.yml config --quiet` | 退出码 0 |
| 上线前体检 | R | `scripts/preflight-deploy.ps1` | 没有 FAIL |
| 完整中间件链路 | R | `scripts/verify-full-stack.ps1` | ok=true，MySQL/Redis/MQ 全部匹配 |
| 部署后业务链路 | R | `scripts/verify-deploy.ps1` | 普通上传、直传、任务、DB、Redis、MinIO 全通过 |
| 指标 | R/M | `/actuator/prometheus`、Grafana | HTTP、任务、线程池和 MQ 标签可查询 |
| HTTPS 边界 | R | Caddy + preflight | 仅 80/443 公网；metrics/Swagger 被代理层拦截 |

## 推荐验证顺序

日常修改：

```powershell
node --check src/main/resources/static/app.js
mvn test
```

涉及上传/播放：

```powershell
mvn test "-Dtest=MediaControllerTests,ChunkUploadServiceTests,DirectUploadServiceTests,S3MediaStorageServiceTests,VideoPlaybackControllerTests"
```

涉及工作流/MQ：

```powershell
mvn test "-Dtest=WorkflowControllerTests,WorkflowProcessorTests,VideoTaskServiceTests,RocketMqWorkflowConsumerTests,StaleWorkflowTaskReaperTests"
```

准备完整演示：

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File scripts\verify-full-stack.ps1
```

## 证据边界

已经证明：

- 单元和 Web 安全边界；
- 真实 Redis/MySQL/RocketMQ 链路；
- MinIO 直传与播放链路；
- MQ 开关在过载场景下的失败率差异；
- 生产 Compose、HTTPS 入口和部署前检查流程。

没有声称：

- 未长期运营公网 SaaS；
- 未承诺生产 QPS、SLA 或最大视频容量；
- Mock AI 结果不代表真实模型质量；
- 单机压测结果不能直接外推到云端集群。

面试中应区分“代码已实现”“自动化已验证”“本地实测”“未来可扩展”，不要把规划讲成已上线事实。
