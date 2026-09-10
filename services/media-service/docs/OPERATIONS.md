# 运维手册（OPERATIONS）

> 合并自原部署/验证/排障文档，只保留可执行内容。参数依据与性能数据见 [PERFORMANCE.md](PERFORMANCE.md)。

## 一、三种运行模式

| 模式 | 启动 | 依赖 |
| --- | --- | --- |
| 轻量 | `mvn spring-boot:run "-Dspring-boot.run.profiles=h2"` | 无（H2 内存库，重启清空） |
| 完整中间件 | `docker compose --profile mysql --profile mq up -d` + 默认启动 | Docker Desktop |
| 观测/对象存储 | 追加 `--profile observability` / `--profile object-storage` | Docker Desktop |

常用地址：工作台 <http://localhost:8081> · Swagger /swagger-ui.html · Health /actuator/health · Grafana <http://localhost:3000> · MinIO 控制台 <http://localhost:19001。>

注意：JDK 25 与 Mockito inline mock 不兼容（`Could not modify all classes`），跑测试用 JDK 17/18；CI 已固定 17。

## 二、验证脚本

```powershell
# 全量测试（受支持 JDK 18，124 个，含真实 JWT 上传与持久化调度 outbox 回归）
mvn test

# 目标环境中间件端到端：注册→分片→MQ 消费→MySQL 持久化→会话清理
# 需要已启动容器及非空 $env:MEDIA_MYSQL_PASSWORD；不是 H2 本地测试的一部分
powershell -NoProfile -ExecutionPolicy Bypass -File scripts\verify-full-stack.ps1 -MysqlPassword $env:MEDIA_MYSQL_PASSWORD

# 公网部署前检查（.env 中所有 CHANGE_ME 已改）
powershell -NoProfile -ExecutionPolicy Bypass -File scripts\preflight-deploy.ps1
powershell -NoProfile -ExecutionPolicy Bypass -File scripts\verify-deploy.ps1
```

## 三、安全底线（部署检查单）

- [ ] `APP_JWT_SECRET` 已配置（非 H2 环境携带默认密钥会拒绝启动）
- [ ] `.env` 中所有 `CHANGE_ME` 已替换（MySQL/MinIO/Grafana/Caddy）
- [ ] `docker-compose.prod.yml` 端口只绑 127.0.0.1，公网入口仅 Caddy
- [ ] Grafana 匿名 Admin 已关闭，配置真实账号
- [ ] `/actuator/prometheus` 不对公网暴露（management 独立端口或反白名单）

## 四、排障速查

| 症状 | 根因方向 |
| --- | --- |
| 上传报「用户不存在」 | 身份语义回归（principal 应为 userId）——跑 `RealJwtUploadFlowTests`；历史事故见下 |
| 启动报 NoClassDefFoundError | 增量编译残留 → `mvn clean package` |
| 直传 UI「网络失败」 | MinIO CORS 未包含前端 origin（compose 已配置，自建环境检查） |
| Redis 连接 7379 而非 6379 | 本机 6379 被系统保留端口占用，映射 7379 是有意为之 |
| 任务长期 TRANSCRIBING | 外部 API 降速/挂起；看 `video_task_processing_seconds`；超 60m 由 reaper 重投 |
| MQ 重复消费告警 | 正常路径：claim 条件 UPDATE 保证只有一个 worker 处理，skip 计数器会 +1 |

## 五、历史事故复盘（保留两条最有价值的）

**1. 真实 JWT 用户上传必报「用户不存在」（P0，测试全绿）**
`JwtAuthenticationFilter` 把 principal 设为 username，而配额校验按 userId 查库；controller 单测用 `.with(user("alice"))` 模拟认证，principal 恰好等于种子 userId，完全掩盖断裂。修复：principal 统一取 userId claim；新增 `RealJwtUploadFlowTests`（真实注册→真实 JWT→真实上传）作为制度性防御。教训：**测试认证方式必须与生产同源**。

**2. 线程池「接收 54/80」曾被当作玄学**
54 = maxPoolSize(4) + queueCapacity(50)，JDK 线程池「队列满才扩容」的直接结果。参数、数据、解释三者在 PERFORMANCE.md 第一节闭环。

## 六、优雅停机与发布

`server.shutdown=graceful`（30s 排空）+ stale-task reaper 兜底：SIGTERM 后在途 HTTP 请求等待完成；被硬中断的处理中任务停留在非终态，60 分钟后被 reaper 重置重投，claim 幂等保证不与幸存 worker 重复。发布顺序无特殊要求，避免连续快速重启即可（两次停机间隔应大于一个任务处理周期）。
