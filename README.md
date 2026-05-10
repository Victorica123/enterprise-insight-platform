# 视频内容理解平台（Video Platform）

基于 Spring Boot 3 + Redis 分片上传 + RocketMQ 异步工作流的视频处理平台。

## 功能特性

- **用户认证**：JWT Token 鉴权，支持注册/登录
- **视频上传**：
  - 单文件直接上传（默认，零依赖）
  - 分片上传（需 Redis）：断点续传、秒传、大文件支持
- **异步处理**：视频转写（Whisper）+ AI 总结（LLM）
- **任务状态轮询**：实时查看处理进度
- **条件装配**：本地开发 / 分布式模式一键切换

## 技术栈

| 层级 | 技术 |
|------|------|
| 后端 | Spring Boot 3.3.5, Java 17 |
| 安全 | Spring Security + JWT |
| 缓存/分片 | Redis 7 |
| 消息队列 | Apache RocketMQ 5.2.0 |
| 前端 | 纯 HTML + CSS + JavaScript |

## 快速开始

### 1. 环境要求

- JDK 17+
- Maven 3.6+
-（可选）Docker Desktop —— 如果你想体验分片上传和 MQ 功能

### 2. 克隆并运行（默认模式：分片上传 + Redis）

```bash
git clone <你的仓库地址>
cd video-platform

# 先启动 Redis（必须，因为默认使用分片上传）
docker-compose up -d redis

# 然后运行项目
mvn spring-boot:run
```

打开浏览器访问 http://localhost:8080，即可体验：
- 注册/登录
- **分片上传**：大文件自动切片、断点续传
- 本地 @Async 异步处理（Mock 转写 + Mock 总结）

> 默认模式**需要 Redis**，用于分片上传的元数据管理和断点续传。

### 3. 纯本地模式（零依赖，单文件上传）

如果你不想装 Redis，可以切换到纯本地模式：

编辑 `src/main/resources/application.yml`：

```yaml
app:
  redis:
    enabled: false     # 关闭 Redis，使用单文件直接上传
  mq:
    enabled: false     # 关闭 RocketMQ，使用本地 @Async
```

然后直接运行：

```bash
mvn spring-boot:run
```

### 4. 启用完整分布式模式（分片上传 + RocketMQ）

#### 4.1 一键启动所有中间件

```bash
docker-compose up -d
```

这会启动：
- Redis 7 → `localhost:6379`
- RocketMQ NameServer → `localhost:9876`
- RocketMQ Broker → `localhost:10911`

#### 4.2 修改配置启用 RocketMQ

编辑 `src/main/resources/application.yml`：

```yaml
app:
  redis:
    enabled: true
  mq:
    enabled: true      # 开启 RocketMQ 异步工作流
```

#### 4.3 重新运行

```bash
mvn spring-boot:run
```

现在你可以体验：
- **分片上传**：大文件自动切片、断点续传、秒传
- **RocketMQ 解耦**：上传后立即返回，视频处理由 MQ 消费者异步执行

### 5. 停止服务

```bash
# 停止 Spring Boot 应用（Ctrl + C）

# 停止 Docker 中间件
docker-compose down
```

## 项目结构

```
video-platform/
├── docker-compose.yml          # Docker 一键启动 Redis + RocketMQ
├── pom.xml
├── README.md
└── src/
    └── main/
        ├── java/com/example/videoplatform/
        │   ├── auth/             # JWT 认证
        │   ├── common/           # 统一响应、全局异常
        │   ├── config/           # 配置类
        │   ├── media/            # 上传服务（单文件 + 分片）
        │   ├── summary/          # AI 总结（Mock / 真实 LLM）
        │   ├── transcript/       # 语音转写（Mock / 真实 Whisper）
        │   └── workflow/         # 任务工作流 + MQ 发布/消费
        └── resources/
            ├── static/           # 前端页面
            └── application.yml   # 主配置
```

## 核心设计亮点

### 1. 分片上传（Redis）

```
POST /api/media/upload/init     → 创建上传会话，返回 uploadId
POST /api/media/upload/chunk    → 逐片上传
POST /api/media/upload/merge    → 合并分片，触发处理
```

- Redis Hash 存储分片元数据（文件名、总分片数）
- Redis Set 记录已上传的分片索引（天然去重）
- 分布式锁防止并发合并导致文件损坏
- MD5 秒传映射减少重复上传

### 2. 异步工作流（RocketMQ）

```
上传完成 → WorkflowPublisher.publish(taskId)
                              ↓
                    ┌─────────────────────┐
                    │ LocalWorkflowPublisher│ 默认：本地 @Async
                    └─────────────────────┘
                    ┌─────────────────────┐
                    │ RocketMqWorkflowPublisher│ 开启后：MQ 发送
                    └─────────────────────┘
                              ↓
                    RocketMqWorkflowConsumer
                              ↓
                    转写 → 总结 → COMPLETED
```

### 3. 条件装配降级

所有分布式组件均使用 `@ConditionalOnProperty`：

| 组件 | 默认 | 条件 |
|------|------|------|
| 锁 | 本地 ReentrantLock | `app.redis.enabled=false` |
| 任务发布 | `@Async` 本地线程池 | `app.mq.enabled=false` |
| 转写/总结 | Mock 数据 | `app.transcript.enabled=false` |

## 面试讲解建议

1. **分片上传**：大文件网络抖动容错、断点续传、Redis 数据结构选型
2. **秒传设计**：MD5 映射，减少重复流量和存储
3. **分布式锁**：`SET NX EX` + Lua 原子解锁
4. **MQ 解耦**：削峰填谷、失败重试、服务解耦
5. **条件装配**：本地开发友好 + 生产可扩展的工程化思维

## License

MIT
