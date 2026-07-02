# 视频内容理解平台

一个基于 Spring Boot 3 的视频内容理解后台系统。项目主线是让真实用户完成“上传视频 -> 自动理解内容 -> 查看转写和总结 -> 管理历史任务”的完整需求；大文件上传、高并发处理和服务器上线是为这个需求服务的工程问题。

## 项目亮点

- 多用户体系：注册、登录、JWT 鉴权，上传和任务查询按用户隔离。
- 视频上传：支持单文件上传，也支持 Redis 分片上传、TTL 会话和合并锁；后续根据用户体验优化并发分片、断点续传、秒传和上传耗时统计。
- 异步工作流：上传后创建任务，后台执行 FFmpeg 音频提取、Whisper 转写、LLM 摘要。
- 用户体验：后续优先补齐任务详情、失败原因、重试提示、历史结果管理和上传/处理耗时反馈。
- 高并发演进：在真实用户访问增长后，通过限流、队列削峰、线程池隔离、幂等和状态机保护支撑多用户同时上传和处理。
- 上线目标：后续提供 Docker/Nginx/HTTPS/MySQL/日志监控等部署能力，让项目可以稳定给真实用户使用。
- 可视化演示：首页展示业务闭环、运行模式、Swagger、Health 和任务状态流水线。
- 条件装配：同一套代码支持本地模式、Redis 模式、Redis + RocketMQ 分布式模式。
- 可测试设计：默认测试不依赖 Redis、RocketMQ、Docker、FFmpeg 或外部 AI API。
- API 文档：集成 Springdoc OpenAPI，可通过 Swagger UI 查看接口。

## 技术栈

| 领域 | 技术 |
| --- | --- |
| 后端 | Java 17, Spring Boot 3.3.5 |
| Web/API | Spring MVC, Bean Validation, Springdoc OpenAPI |
| 安全 | Spring Security, JWT |
| 数据库 | JPA, H2, MySQL profile |
| 缓存/锁 | Redis, Redisson |
| 消息队列 | RocketMQ |
| AI 工作流 | FFmpeg, Whisper-compatible API, OpenAI-compatible LLM API |
| 前端 | 原生 HTML, CSS, JavaScript |
| 测试 | JUnit 5, AssertJ, Mockito, Spring Boot Test |

## 架构模式

项目通过配置开关支持三种运行方式：

| 模式 | 配置 | 用途 |
| --- | --- | --- |
| 本地轻量模式 | `APP_REDIS_ENABLED=false`, `APP_MQ_ENABLED=false` | 不依赖中间件，适合快速开发和面试演示 |
| 默认 Redis 模式 | `APP_REDIS_ENABLED=true`, `APP_MQ_ENABLED=false` | 支持分片上传，本地异步处理 |
| 分布式模式 | `APP_REDIS_ENABLED=true`, `APP_MQ_ENABLED=true` | Redis + RocketMQ，适合讲解横向扩展 |

核心链路：

```text
注册/登录 -> 上传视频 -> 创建 VideoTask -> 发布工作流任务
-> FFmpeg 提取音频 -> Whisper 转写 -> LLM 摘要 -> 查询任务结果
```

## 需求落地路线

项目后续先围绕用户需求迭代，再解决阻碍需求落地的工程问题：

1. 核心需求：用户能注册登录、上传视频、看到处理状态、获得转写和总结、回看历史任务。
2. 体验问题：上传和处理等待时间要可见，失败原因要清楚，必要时能重试。
3. 大文件问题：当大视频上传慢时，建立上传耗时基线，再实现并发分片、失败 chunk 重试、断点续传和秒传。
4. 上线问题：补齐 MySQL migration、Docker 部署、Nginx/HTTPS、上传大小限制、日志监控和文件清理策略。
5. 并发问题：当真实用户变多后，用限流、队列、线程池隔离、幂等和状态机保护避免服务被拖垮。

需求和优化都必须可验证，后续会记录这些指标：

- 文件大小、chunk size、chunk 数量。
- 上传总耗时、平均 chunk 耗时、merge 耗时。
- 任务排队时间、转写耗时、总结耗时。
- 并发用户数、成功率、失败原因和重试次数。

## 快速启动

### 环境要求

- JDK 17+
- Maven 3.8+
- 可选：Docker Desktop，用于启动 Redis/RocketMQ/MySQL 等中间件
- 可选：FFmpeg，用于真实音频提取

### 方式一：本地轻量模式

适合第一次运行和面试演示，不需要 Redis、RocketMQ、外部 AI API。

```powershell
$env:APP_REDIS_ENABLED="false"
$env:APP_MQ_ENABLED="false"
$env:APP_TRANSCRIPT_ENABLED="false"
$env:APP_SUMMARY_ENABLED="false"
$env:SPRING_DOCKER_COMPOSE_ENABLED="false"
$env:MANAGEMENT_HEALTH_REDIS_ENABLED="false"
mvn spring-boot:run
```

启动后访问：

- 前端页面：http://localhost:8081
- API 文档：http://localhost:8081/swagger-ui.html
- 健康检查：http://localhost:8081/actuator/health

### 方式二：默认 Redis 模式

适合展示分片上传。

```powershell
docker compose up -d redis
$env:APP_REDIS_ENABLED="true"
$env:APP_MQ_ENABLED="false"
mvn spring-boot:run
```

### 方式三：Redis + RocketMQ 分布式模式

适合面试时讲分布式架构，但本地启动成本更高。

```powershell
docker compose --profile mq up -d
$env:APP_REDIS_ENABLED="true"
$env:APP_MQ_ENABLED="true"
mvn spring-boot:run
```

## 常用命令

```powershell
# 运行全部测试
mvn test

# 清理后编译
mvn clean compile

# 打包
mvn clean package -DskipTests

# 运行指定测试
mvn test "-Dtest=WorkflowProcessorTests"
```

## API 入口

| 功能 | 路径 |
| --- | --- |
| 注册 | `POST /api/auth/register` |
| 登录 | `POST /api/auth/login` |
| 单文件上传 | `POST /api/media/upload/file` |
| 初始化分片上传 | `POST /api/media/upload/init` |
| 上传分片 | `POST /api/media/upload/chunk` |
| 合并分片 | `POST /api/media/upload/merge` |
| 查询我的任务 | `GET /api/workflow/tasks` |
| 查询任务详情 | `GET /api/workflow/tasks/{taskId}` |
| API 文档 | `GET /swagger-ui.html` |
| OpenAPI JSON | `GET /v3/api-docs` |

除注册、登录、健康检查和 API 文档外，业务接口都需要 `Authorization: Bearer <token>`。

## 面试讲解重点

建议按这个顺序讲：

1. 用户需求：用户上传视频后，要稳定拿到可用的转写和总结，并能管理历史任务。
2. 页面演示：从首页“面试演示台”讲业务闭环和三种运行模式。
3. 用户隔离：每个任务和上传会话都绑定当前登录用户。
4. 上传设计：单文件上传用于轻量模式，Redis 分片上传用于大文件、断点续传和后续体验优化。
5. 工作流设计：`WorkflowPublisher` 抽象本地异步和 RocketMQ 两种调度方式，用队列削峰处理耗时任务。
6. 工程取舍：大文件、高并发、部署和监控都服务于用户需求，不为了技术而技术。
7. 事务边界：工作流状态在 `@Transactional` 方法中推进，失败时落库为 `FAILED`。
8. 稳定性：错误信息截断、FFmpeg 临时文件清理、外部 API mock fallback。
9. 测试策略：核心边界用单元测试锁住，测试环境不依赖中间件。

## 当前测试覆盖

当前测试覆盖点包括：

- 视频文件名和 content-type 校验。
- Mock 摘要空白输入和长文本截断。
- 工作流成功、总结失败、长错误信息截断。
- 爬取服务空白站点参数防御。
- JWT 鉴权、Controller 用户隔离、上传越权、分片边界、合并锁和清理。
- Spring Boot 上下文在无 Redis/MQ/Docker 环境下启动。

运行：

```powershell
mvn test
```

## 求职路线图

后续迭代计划见 [CAREER_ROADMAP.md](docs/CAREER_ROADMAP.md)。

建议下一阶段继续推进：

- 核心体验确认：上传、任务状态、结果展示、历史任务是否满足真实用户需求。
- 体验补齐：任务详情、失败原因、重试提示、上传/处理耗时反馈。
- 上传性能基线：记录总耗时、chunk 耗时、merge 耗时，为后续大文件优化做对照。
- Flyway/Liquibase 数据库迁移。
- Dockerfile、Nginx/HTTPS、GitHub Actions、日志监控和服务器部署。

---

## 2026-07-01 当前可验证能力

- 首页提供上传实验面板，可切换普通上传和 Redis 并发分片上传。
- Redis 分片上传当前前端并发数为 `4`，用于观察并发 chunk 对上传耗时的影响。
- 上传观测面板显示最近一次上传结果，并保留普通上传和 Redis 分片上传的最近对比记录；切换上传方式不会污染历史记录。
- 历史任务支持删除，接口为 `DELETE /api/workflow/tasks/{taskId}`，按当前登录用户做 owner 校验。
- Docker Compose 中 Redis 使用宿主机 `7379` 端口映射到容器 `6379`，用于避开本机 Windows 保留端口段。
- Docker Compose 中 MySQL 使用 `mysql` profile，适合验证 H2 切换到 MySQL 后用户和任务是否能持久化。

Redis 模式启动：

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

MySQL + Redis 模式启动：

```powershell
docker compose --profile mysql up -d redis mysql
$env:MYSQL_HOST="localhost"
$env:MYSQL_PORT="3306"
$env:MYSQL_DATABASE="videoplatform"
$env:MYSQL_USERNAME="root"
$env:MYSQL_PASSWORD="123456"
$env:APP_REDIS_ENABLED="true"
$env:APP_MQ_ENABLED="false"
$env:APP_TRANSCRIPT_ENABLED="false"
$env:APP_SUMMARY_ENABLED="false"
$env:SPRING_DOCKER_COMPOSE_ENABLED="false"
$env:SPRING_DATA_REDIS_PORT="7379"
mvn spring-boot:run "-Dspring-boot.run.profiles=mysql"
```

快速验证：

```powershell
.\smoke-test.ps1
```

重要结论：

Redis 分片上传不一定比普通上传更快。Redis 提供的是上传会话、chunk 状态、merge 锁以及后续断点续传、失败重试、秒传的基础。真正的提速来自并发 chunk 上传、chunk size 调优和失败 chunk 重试。RocketMQ 解决的是上传后的异步处理和削峰，不直接加速文件上传。
