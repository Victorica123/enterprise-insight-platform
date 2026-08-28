# Enterprise Insight Platform

企业多模态需求洞察与执行平台：统一接入客户访谈、需求评审、故障复盘视频与业务文档，完成可靠上传、异步转写、证据化问答、需求分析、PRD 生成和行动项审批。

本仓库采用一个产品、一个仓库、两个后端服务、一个前端：

- `services/media-service`：Spring Boot 媒体上传、存储、转写与可靠异步工作流。
- `services/agent-service`：FastAPI Agentic RAG、证据门控、分析编排与受控工具。
- `apps/web`：统一 React 工作台。
- `contracts`：跨服务 API 与领域事件契约。
- `knowledge`：产品、架构、数据和质量知识库。

当前处于整合阶段。原项目保留不动，迁移过程以纵向业务链路和自动化回归为准。
