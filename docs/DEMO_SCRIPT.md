# 面试演示脚本

目标：用 3 分钟展示这个项目不是简单 CRUD，而是一个完整的后端工程项目。

## 演示前准备

推荐使用本地轻量模式，避免中间件或外部 API 影响演示。

```powershell
$env:APP_REDIS_ENABLED="false"
$env:APP_MQ_ENABLED="false"
$env:APP_TRANSCRIPT_ENABLED="false"
$env:APP_SUMMARY_ENABLED="false"
$env:SPRING_DOCKER_COMPOSE_ENABLED="false"
$env:MANAGEMENT_HEALTH_REDIS_ENABLED="false"
mvn spring-boot:run
```

打开：

- 前端页面：http://localhost:8081
- API 文档：http://localhost:8081/swagger-ui.html
- 健康检查：http://localhost:8081/actuator/health

## 3 分钟讲解顺序

### 0:00 - 0:30 打开首页讲需求

可以这样说：

> 这是一个视频内容理解平台。用户登录后上传视频，系统自动创建任务，后台完成音频提取、语音转写和 AI 总结，最后用户可以查看自己的历史结果。页面上的演示台展示了业务闭环：登录、上传、任务、转写、总结、结果。

页面上重点指：

- 面试演示台：业务闭环和三种运行模式。
- Swagger API：接口文档入口。
- Health Check：服务健康检查入口。
- 状态流水线：上传、排队、转写、总结、完成。

### 0:30 - 1:30 完成一次用户链路

展示：

1. 注册或登录用户。
2. 选择一个小视频。
3. 点击上传。
4. 观察状态流水线变化。
5. 打开“我的视频”，说明历史任务按当前用户隔离。

可以这样说：

> 这不是只做了一个上传按钮。后端会把上传行为转成一个可追踪的 VideoTask，前端用状态流水线展示任务生命周期。登录用户只能看到自己的任务，这对应真实系统里的数据隔离要求。

### 1:30 - 2:10 接口和运行模式

展示：

1. 打开 http://localhost:8081/swagger-ui.html。
2. 打开 http://localhost:8081/actuator/health。
3. 回到首页演示台的运行模式。

可以这样说：

> API 文档由 Springdoc OpenAPI 自动生成，接口变更后文档能同步更新。系统支持本地异步、Redis 分片上传、Redis + RocketMQ 三种模式，所以面试演示可以轻量运行，生产扩展时也有架构空间。

### 2:10 - 2:45 技术亮点

重点讲 4 个点：

- 用户隔离：所有上传 session 和任务查询都绑定当前认证用户。
- 条件装配：Redis、RocketMQ、Whisper、LLM 都可以通过配置开关启用或关闭。
- 事务边界：工作流失败会把任务状态持久化为 `FAILED`，避免任务卡死。
- 可测试性：核心边界测试不依赖 Redis、RocketMQ、Docker 或外部 API。

### 2:45 - 3:00 后续规划

可以这样说：

> 下一步我会把它继续往生产化作品推进：数据库 migration、任务幂等、MQ 重复消费保护、结构化日志和 Docker/GitHub Actions。

## 一句话背诵版

> 我这个项目不是简单 CRUD，而是一个视频处理后台系统：前端完成登录、上传和结果展示，后端负责 JWT 用户隔离、文件上传、任务状态机、异步处理和可选 Redis/MQ 扩展；测试重点覆盖鉴权、越权、上传边界和工作流失败。

## 面试官可能追问

### 为什么支持三种部署模式？

回答方向：

> 开发和面试演示不应该强依赖中间件，所以保留本地轻量模式。Redis 模式用于展示分片上传和锁。RocketMQ 模式用于展示任务解耦和横向扩展能力。

### 为什么上传合并需要锁？

回答方向：

> merge 是有副作用的操作，会写文件、清 Redis、创建任务。如果用户重复点击或请求重试，锁可以避免重复合并和生成脏数据。后续还可以继续做幂等返回。

### 为什么工作流要有事务？

回答方向：

> 状态、转写结果、摘要和失败原因属于同一个任务生命周期。如果中途异常，事务边界可以保证失败状态被统一处理，避免任务长期卡在处理中。

### 为什么测试不依赖 Redis/MQ？

回答方向：

> 单元测试应该稳定、快速、低成本。Redis/MQ 可以放到后续集成测试里；当前测试先覆盖业务边界和状态流转。

## 演示失败时的备用方案

- 服务启动失败：执行 `mvn clean compile`。
- 端口占用：修改 `src/main/resources/application.yml` 中的 `server.port`。
- 登录后 403：浏览器控制台执行 `localStorage.clear(); location.reload();`。
- 上传接口 503：当前是 Redis 分片上传未启用，可以改用单文件上传或开启 Redis。

---

## Redis 上传实验演示补充（2026-07-01）

启动 Redis 模式：

```powershell
docker compose up -d redis
$env:APP_REDIS_ENABLED="true"
$env:APP_MQ_ENABLED="false"
$env:APP_TRANSCRIPT_ENABLED="false"
$env:APP_SUMMARY_ENABLED="false"
$env:SPRING_DOCKER_COMPOSE_ENABLED="false"
$env:SPRING_DATA_REDIS_PORT="7379"
mvn spring-boot:run
```

演示步骤：

1. 打开首页并登录。
2. 选择同一个视频文件。
3. 先选择“普通上传”，点击开始上传，观察“上传观测”的总耗时和吞吐。
4. 再选择“Redis 分片”，点击开始上传，观察 chunk 数、平均 chunk 耗时、初始化和合并耗时。
5. 对比“最近普通上传”和“最近 Redis 分片”。
6. 在“我的视频”中删除不需要的历史任务，说明历史记录支持用户自主管理。

推荐解释：

> Redis 分片上传不等于天然更快。Redis 主要保存上传会话、chunk 状态和 merge 锁，为失败重试、断点续传和秒传打基础。真正的上传提速来自并发 chunk 上传、chunk size 调优和失败 chunk 重试。RocketMQ 解决的是上传后的任务削峰和异步处理，不直接加速浏览器到服务器的文件传输。

验证命令：

```powershell
.\smoke-test.ps1
```

预期输出包含：

```text
Smoke test passed
```
