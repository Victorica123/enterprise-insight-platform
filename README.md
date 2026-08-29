# Enterprise Insight Platform

企业多模态需求洞察与执行平台：统一接入客户访谈、需求评审、故障复盘视频与业务文档，完成可靠上传、异步转写、证据化问答、需求分析、PRD 生成和行动项审批。

本仓库采用一个产品、一个仓库、两个后端服务、一个前端：

- `services/media-service`：Spring Boot 媒体上传、存储、转写与可靠异步工作流。
- `services/agent-service`：FastAPI Agentic RAG、证据门控、分析编排与受控工具。
- `apps/web`：统一 React 工作台。
- `contracts`：跨服务 API 与领域事件契约。
- `knowledge`：产品、架构、数据和质量知识库。

当前已贯通统一登录、视频转写入库、时间戳证据问答、六阶段分析等待/恢复和证据化 PRD 草稿。原项目保留不动，迁移过程以纵向业务链路和自动化回归为准。

## 无域名本地验收

安装 Python 基础依赖、Maven 与 JDK 17/18 后，在仓库根目录执行：

```powershell
pip install -r services/agent-service/requirements.txt
python scripts/local_acceptance.py
```

脚本只使用随机 `127.0.0.1` 端口、临时 H2/SQLite、本地文件和 mock/local AI，不要求 Docker、Redis、RocketMQ、对象存储、外部模型、服务器或域名。

统一前端开发入口：

```powershell
cd apps/web
npm ci
npm run dev
```

当前正式 PRD 发布策略仍等待个人 Workspace 审批规则确认；DRAFT 不会自动发布为正式知识。
