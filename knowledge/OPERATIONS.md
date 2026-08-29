# 运维知识

## 支持的本地工具链

- Media Service：以其 Maven 配置声明的 JDK 17/18 为准。
- Agent Service：Python 版本与依赖以 `services/agent-service` 的运行文件为准。
- Web：Node.js 版本与依赖以 `apps/web/package.json` 和锁文件为准。

核心验收必须可使用 H2、SQLite、本地媒体目录、mock 转写/摘要和 localhost HTTP 完成；外部模型、Redis、RocketMQ、S3 与正式域名属于独立的真实集成验证，不阻塞本地功能验收。

根目录提供可重复的本地纵向验收：

```powershell
python scripts/local_acceptance.py
```

脚本自动构建并启动两个后端到随机 `127.0.0.1` 端口，使用临时 H2、SQLite、本地媒体目录、mock 转写/摘要和本地模板回答；除个人全链路外，还会注册第二个用户，验证团队创建、一次性邀请、显式切换、跨成员视频与 Agent 共享、个人隔离、团队四眼发布、知识/工单交付和 VIEWER 只读。它不访问公网，也不要求 Docker、域名、Redis、RocketMQ、S3 或模型 Key。失败日志会保存在系统临时目录并打印路径。

需要持久数据和统一浏览器入口时使用根目录 Compose：

```powershell
./scripts/start_local.ps1 -Build
# 浏览 http://127.0.0.1:8080
./scripts/stop_local.ps1
```

Web 只绑定 `127.0.0.1`，nginx 同源代理 `/agent` 与 `/media`；H2、SQLite 和媒体文件保存在已忽略的 `runtime/`。完整步骤见 `docs/LOCAL_RELEASE_RUNBOOK.md`。

统一 Web 本地启动：

```powershell
cd apps/web
npm ci
npm run dev
```

默认连接 `127.0.0.1:8081` 的 Media Service 与 `127.0.0.1:8000` 的 Agent Service；可分别用 `VITE_MEDIA_API_BASE_URL`、`VITE_API_BASE_URL` 覆盖。

## 配置原则

- 密钥只通过环境变量或密钥服务注入，不进入仓库和事件。
- JWT issuer/audience/signing trust、内部服务地址、队列和存储使用显式环境变量。
- 启动时验证关键配置，避免以不安全默认值静默进入生产模式。
- 开发 light/mock 配置与真实集成配置分开命名并在健康接口中可识别。

## 可观测性

- `trace_id` 从前端/网关贯穿媒体任务、事件投递、Agent 摄取、问答和工具调用。
- 指标至少覆盖队列积压、各阶段延迟、失败/重试、事件重复与冲突、引用验证失败、等待确认时长和审批结果。
- 错误对用户提供可操作原因，对日志保留结构化内部原因且不泄露敏感数据。

## 恢复策略

- 媒体任务可安全重试，不能重复创建资产。
- 转写事件可重放，Agent 消费必须幂等。
- Agent 会话从持久化检查点恢复。
- 发布 PRD、知识合并和外部写操作使用幂等键及审计记录。
- 停止本地栈后可用 `python scripts/local_data.py backup` 创建带 SHA-256 manifest 的归档；`verify` 校验文件与 SQLite，`restore --force` 覆盖前自动创建 pre-restore 安全备份。

## 当前运行状态与缺口

统一 localhost Compose、启动/停止脚本、备份校验恢复工具、本地发布手册和本地质量目标已提供。无容器验收链路已实际通过；当前主机没有 Docker，因此 Compose 本轮只完成静态配置校验，不能声明容器运行已验证。

真实 Redis、RocketMQ、MySQL、S3、外部模型与正式身份提供方 smoke，生产数据库迁移编排、灾备演练、监控告警接入和生产 SLO 批准仍待目标环境与业务决策。`docs/SLO.md` 中的生产数值只是候选项，不是已经兑现的服务承诺。
