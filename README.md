# Enterprise Insight Platform

企业多模态需求洞察与执行平台：统一接入客户访谈、需求评审、故障复盘视频与业务文档，完成可靠上传、异步转写、证据化问答、需求分析、PRD 生成和行动项审批。

本仓库采用一个产品、一个仓库、两个后端服务、一个前端：

- `services/media-service`：Spring Boot 媒体上传、存储、转写与可靠异步工作流。
- `services/agent-service`：FastAPI Agentic RAG、证据门控、分析编排与受控工具。
- `apps/web`：统一 React 工作台。
- `contracts`：跨服务 API 与领域事件契约。
- `knowledge`：产品、架构、数据和质量知识库。

当前已贯通统一登录、视频转写入库、时间戳证据问答、六阶段分析等待/恢复、证据化 PRD 和人工发布审批。个人 Workspace 使用 OWNER 二次确认，团队 Workspace 使用不同成员四眼审批；两种路径都保留审计链。

## 无域名本地验收

安装 Python 基础依赖、Maven 与 JDK 17/18 后，在仓库根目录执行：

```powershell
pip install -r services/agent-service/requirements.txt
python scripts/local_acceptance.py
```

脚本只使用随机 `127.0.0.1` 端口、临时 H2/SQLite、本地文件和 mock/local AI，不要求 Docker、Redis、RocketMQ、对象存储、外部模型、服务器或域名。验收覆盖真实 JWT、视频证据、PRD 生成、个人空间二次发布确认和不可变审计。

统一前端开发入口：

```powershell
cd apps/web
npm ci
npm run dev
```

PRD 不会由 Agent 静默发布：必须经过服务端 Workspace 策略决定的人工审批，才能从 `DRAFT_READY` 进入 `PUBLISHED`。
