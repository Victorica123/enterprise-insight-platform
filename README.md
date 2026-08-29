# Enterprise Insight Platform

企业多模态需求洞察与执行平台：统一接入客户访谈、需求评审、故障复盘视频与业务文档，完成可靠上传、异步转写、证据化问答、需求分析、PRD 生成和行动项审批。

本仓库采用一个产品、一个仓库、两个后端服务、一个前端：

- `services/media-service`：Spring Boot 媒体上传、存储、转写与可靠异步工作流。
- `services/agent-service`：FastAPI Agentic RAG、证据门控、分析编排与受控工具。
- `apps/web`：统一 React 工作台。
- `contracts`：跨服务 API 与领域事件契约。
- `knowledge`：产品、架构、数据和质量知识库。

当前已贯通统一登录、个人/团队 Workspace 创建邀请与切换、团队资源共享与个人隔离、视频转写入库、时间戳证据问答、六阶段分析等待/恢复、证据化 PRD、人工发布审批、不可变 PRD 版本、知识候选审批与行动项工单审批。个人 Workspace 使用 OWNER 二次确认，团队 Workspace 使用不同成员四眼审批；两种路径都保留审计链。

完整的代码框架、纵向数据流、RAG/Embedding、缓存、可靠性和面试技术点见 [`knowledge/TECHNICAL_IMPLEMENTATION.md`](knowledge/TECHNICAL_IMPLEMENTATION.md)。项目维护 Skill 已接入可再生语义索引，用 Top-K 原文路由降低重复上下文加载。

## 无域名本地验收

安装 Python 基础依赖、Maven 与 JDK 17/18 后，在仓库根目录执行：

```powershell
pip install -r services/agent-service/requirements.txt
python scripts/local_acceptance.py
```

脚本只使用随机 `127.0.0.1` 端口、临时 H2/SQLite、本地文件和 mock/local AI，不要求 Docker、Redis、RocketMQ、对象存储、外部模型、服务器或域名。验收覆盖真实 JWT、视频证据、PRD 生成、个人空间二次发布确认、团队邀请/切换/跨成员共享/四眼审批、个人隔离、VIEWER 只读、不可变版本、知识候选人工决定和行动项工单审批。

需要保留数据的本地工作台可使用统一 Compose：

```powershell
./scripts/start_local.ps1 -Build
```

浏览器入口为 `http://127.0.0.1:8080`；数据保存在忽略提交的 `runtime/`。停止服务后可运行 `python scripts/local_data.py backup`，完整步骤见 `docs/LOCAL_RELEASE_RUNBOOK.md`。

统一前端开发入口：

```powershell
cd apps/web
npm ci
npm run dev
```

PRD 不会由 Agent 静默发布：必须经过服务端 Workspace 策略决定的人工审批，才能从 `DRAFT_READY` 进入 `PUBLISHED`。
