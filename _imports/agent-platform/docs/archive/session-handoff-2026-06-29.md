# 任务接续手册：2026-06-29

> 用途：如果后续在新的对话窗口继续本项目，先把这份文件发给 AI，AI 就能快速准确了解项目目标、当前进度、已完成内容和下一步任务。

## 1. 项目总目标

项目名称：

```text
企业智能工单与知识助手平台
Enterprise AI Workflow Assistant
```

项目定位：

```text
面向企业内部知识问答、工单处理和风险分析的 AI 工作流平台。
```

长期目标：

- 支持私有知识库问答。
- 支持 Agentic RAG。
- 支持 GraphRAG 关系分析。
- 支持 MCP 风格工具调用。
- 支持多 Agent 工作流。
- 支持 Human-in-the-loop 人工审批。
- 支持 tracing、eval 和 token 成本监控。

当前阶段：

```text
V1：知识库问答系统
```

V1 当前目标：

```text
上传 txt/md 文档 -> 文档切块 -> 持久化保存 -> 检索相关 chunk -> local/api/auto 生成回答 -> 展示来源证据
```

## 2. 今天完成的主要内容

今天已经从空项目推进到一个可运行的 V1 原型，包括后端、持久化、API 生成模式和前端工作台。

已完成：

1. 创建项目规划文档。
2. 创建 FastAPI 后端。
3. 实现文档上传接口。
4. 支持 `.txt` / `.md` 文件。
5. 实现文档切块。
6. 实现中文友好的关键词/字符片段检索。
7. 实现延期原因类问题的规则式因果抽取。
8. 接入 DeepSeek / OpenAI 兼容 API。
9. 增加回答模式选择：`local` / `api` / `auto`。
10. 使用 SQLite 持久化保存文档和 chunk。
11. 新增文档列表接口。
12. 创建 React/Vite 前端工作台。
13. 前端支持上传、文档列表、提问、模式选择、回答展示和来源展示。
14. 后端已添加 CORS，允许前端从 `5173` 调用后端 `8000`。
15. 前端 `npm install` 和 `npm run build` 已验证通过。
16. 2026-06-30 继续开发：新增文档删除接口和前端删除按钮。
17. 2026-06-30 继续开发：新增 `docs/troubleshooting-log.md`，记录 `Failed to fetch` 排查方法；前端 fetch 网络错误提示已优化。
18. 2026-06-30 继续开发：新增 PDF 上传支持，后端优先使用 PyMuPDF，回退到 pypdf 提取 PDF 文本。
19. 2026-06-30 继续开发：关闭 VPN 后 PyMuPDF 和 pypdf 安装成功，PDF 解析、入库和检索链路已验证。
20. 2026-06-30 继续开发：新增中文 PDF 测试样本 `docs/sample-project-delay-cn.pdf`，并优化中文 PDF 文本清洗和延期字段抽取。
21. 2026-06-30 继续开发：新增 `/chat` 执行轨迹 trace，前端新增执行轨迹面板。
22. 2026-06-30 继续开发：新增 V2-lite 本地 query 扩展，提升延期/风险/负责人类问题检索命中。
23. 2026-06-30 继续开发：新增 evidence_check，基于最高分、强相关来源和意图覆盖判断是否回答。
24. 2026-06-30 继续开发：优化 evidence_check 为按问题类型动态门控，并将设计说明合并到 `docs/troubleshooting-log.md`。
25. 2026-06-30 继续开发：新增 `apps/api/app/retrievers.py`，将关键词检索从 `rag.py` 拆成 Retriever 抽象层，为 embedding 检索做准备。

## 3. 当前项目结构

```text
D:\multi agents
  README.md
  enterprise-ai-workflow-assistant-plan.md
  .gitignore

  docs/
    v1-guide.md
    v1-task-list.md
    troubleshooting-log.md
    session-handoff-2026-06-29.md

  apps/
    api/
      README.md
      requirements.txt
      .env
      .env.example
      app/
        __init__.py
        main.py
        models.py
        rag.py
        retrievers.py
        llm.py
        config.py
        database.py
      data/
        knowledge_base.sqlite3

    web/
      README.md
      package.json
      index.html
      tsconfig.json
      vite.config.ts
      src/
        api.ts
        main.tsx
        styles.css
        vite-env.d.ts
```

说明：

- `apps/api/data/` 已加入 `.gitignore`，数据库文件是本地运行产物。
- `apps/api/.env` 已加入 `.gitignore`，里面包含本地 API 配置，不应提交或公开。
- `apps/api/.env.example` 是安全模板，不包含真实 key。

## 4. 后端当前能力

后端路径：

```text
apps/api
```

后端技术：

```text
FastAPI + SQLite + DeepSeek/OpenAI 兼容 API
```

当前接口：

### 4.1 健康检查

```http
GET /health
```

返回：

```json
{
  "status": "ok"
}
```

### 4.2 上传文档

```http
POST /documents
```

请求类型：

```text
multipart/form-data
```

字段：

```text
file: .txt 或 .md 文件
```

作用：

- 读取文档内容。
- 切成 chunk。
- 写入 SQLite。

### 4.3 查看文档列表

```http
GET /documents
```

返回示例：

```json
[
  {
    "document_id": "...",
    "filename": "sample.md",
    "chunk_count": 1,
    "created_at": "2026-06-29 09:09:52"
  }
]
```

### 4.4 删除文档

```http
DELETE /documents/{document_id}
```

作用：

- 删除 document。
- 删除对应 chunks。
- 文档不存在时返回 404。

返回示例：

```json
{
  "status": "deleted",
  "document_id": "..."
}
```

### 4.5 提问

```http
POST /chat
```

请求示例：

```json
{
  "question": "客户 A 的项目为什么延期？",
  "answer_mode": "local"
}
```

`answer_mode` 可选值：

```text
local：只使用内部 RAG 规则/模板，不调用外部 API。
api：调用 DeepSeek / OpenAI 兼容 API 基于来源生成回答。
auto：自动选择。延期原因类问题优先走内部规则；其他问题如果配置了 API Key，就调用 API。
```

返回包含：

- `answer`
- `sources`
- `trace`

`trace` 示例步骤：

- `question_received`
- `retrieve`
- `select_sources`
- `answer`

## 5. 后端关键文件说明

### `apps/api/app/main.py`

FastAPI 入口。

负责：

- 加载 `.env`
- 初始化 SQLite
- 配置 CORS
- 注册接口：
  - `/health`
  - `/documents`
  - `/chat`

### `apps/api/app/models.py`

Pydantic 数据模型。

包含：

- `DocumentUploadResponse`
- `DocumentSummary`
- `ChatRequest`
- `Source`
- `ChatResponse`

### `apps/api/app/database.py`

SQLite 数据库模块。

负责：

- 自动创建数据库文件。
- 创建 `documents` 表。
- 创建 `chunks` 表。
- 插入文档和 chunk。
- 查询文档列表。
- 查询全部 chunk。
- 删除文档和对应 chunk。

数据库位置：

```text
apps/api/data/knowledge_base.sqlite3
```

### `apps/api/app/rag.py`

RAG 主逻辑。

负责：

- 文档切块。
- 文档写入数据库。
- 调用 Retriever 检索相关 chunk。
- 构建 `sources`。
- 执行 evidence_check 证据门控。
- 根据 `answer_mode` 生成回答。
- 对延期原因类问题进行规则式因果抽取。

当前检索方式：

```text
关键词 + 中文单字 + 中文相邻双字片段
```

注意：

这只是学习版检索。后续应升级为 embedding + pgvector。

### `apps/api/app/retrievers.py`

检索器模块。

当前包含：

- `Retriever` 接口。
- `KeywordRetriever` 关键词检索器。
- `RetrievalHit` 和 `RetrievalResult` 检索结果结构。

后续接 embedding 时，优先新增 `EmbeddingRetriever`，不要把向量检索逻辑重新塞回 `rag.py`。

### `apps/api/app/llm.py`

LLM API 调用模块。

当前使用 OpenAI SDK 调 DeepSeek 兼容接口。

配置来自 `.env`：

```text
LLM_PROVIDER=deepseek
DEEPSEEK_BASE_URL=https://api.deepseek.com
DEEPSEEK_MODEL=deepseek-v4-flash
DEEPSEEK_API_KEY=...
DEFAULT_ANSWER_MODE=local
```

注意：

真实 key 不要写进公开文档或提交到仓库。

### `apps/api/app/config.py`

配置加载模块。

负责：

- 自动读取项目根目录 `.env`
- 自动读取 `apps/api/.env`
- 提供 LLM 配置
- 提供默认回答模式

## 6. 前端当前能力

前端路径：

```text
apps/web
```

前端技术：

```text
React + Vite + TypeScript + CSS + lucide-react
```

当前页面是一个工作台，不是 landing page。

布局：

```text
左侧：
  - 项目标题
  - 文档上传
  - 文档列表

右侧：
  - 问答标题
  - answer_mode 切换按钮：auto/local/api
  - 问题输入框
  - 回答展示
  - 来源证据展示
```

前端关键文件：

### `apps/web/src/api.ts`

封装后端请求：

- `listDocuments`
- `uploadDocument`
- `askQuestion`

默认 API 地址：

```text
http://127.0.0.1:8000
```

可通过前端 `.env` 修改：

```text
VITE_API_BASE_URL=http://127.0.0.1:8000
```

### `apps/web/src/main.tsx`

React 主页面。

负责：

- 管理文档列表状态。
- 管理上传状态。
- 管理删除文档状态。
- 管理问题输入。
- 管理回答模式。
- 调用 `/chat`。
- 展示回答和来源。
- 删除文档后刷新列表。
- 展示执行轨迹。

### `apps/web/src/styles.css`

前端样式。

设计风格：

- 工作台风格。
- 左侧知识库栏。
- 右侧问答区域。
- 不做营销型首页。
- 使用克制的白/灰/青绿色配色。

## 7. 启动方式

### 7.1 启动后端

```powershell
cd "D:\multi agents\apps\api"
uvicorn app.main:app --reload --port 8000
```

后端 Swagger：

```text
http://127.0.0.1:8000/docs
```

### 7.2 启动前端

```powershell
cd "D:\multi agents\apps\web"
npm run dev
```

前端页面：

```text
http://127.0.0.1:5173
```

## 8. 已验证内容

已验证：

- Python 语法检查通过。
- 后端基础函数测试通过。
- SQLite 持久化测试通过。
- 上传文档后，`GET /documents` 能查到。
- 重启后可以找到之前上传的文件。
- local 模式可以回答延期原因。
- DeepSeek API 配置已加入本地 `.env`。
- 前端依赖安装成功。
- 前端 `npm run build` 成功。
- 2026-06-30：后端删除接口和前端删除按钮代码已完成。
- 2026-06-30：定位一次上传时报 `Failed to fetch`，实际原因为 `127.0.0.1:8000` 后端未运行或端口不可连接。
- 2026-06-30：PDF 依赖安装后，使用临时 PDF 验证了 `parse_document()`、入库和检索链路。
- 2026-06-30：中文 PDF 测试样本可解析，local 模式可抽取延期原因、原计划、调整后日期、负责人和合同风险。
- 2026-06-30：trace 验证通过，可看到问题接收、检索命中、来源选择和回答路径。

未完全验证：

- 内置浏览器插件访问 `http://127.0.0.1:5173` 被安全策略拦截，所以没有通过 Codex 内置浏览器截图验证页面。
- 用户可以用自己的浏览器打开 `http://127.0.0.1:5173` 验证。

## 9. 重要设计决策

### 9.1 为什么先用 SQLite

因为用户是转码新手，直接上 PostgreSQL + pgvector 容易同时遇到太多问题。

SQLite 让用户先理解：

- 表结构
- 文档持久化
- chunk 持久化
- 服务重启后数据不丢
- 后端如何从数据库读取 chunk

后续再升级到 PostgreSQL + pgvector。

### 9.2 为什么 local/api/auto 都保留

`local`：

- 不花 API 成本。
- 便于学习 RAG 数据流。
- 对延期原因类问题可以规则式抽取。

`api`：

- 让 DeepSeek 基于来源做自然语言总结。
- 更接近真实 AI 产品体验。

`auto`：

- 给用户一个默认智能选择。
- 简单明确的延期原因问题优先走 local 规则。
- 其他复杂总结问题优先走 API。

### 9.3 为什么现在还没做 embedding

当前检索方式是学习版。

embedding + pgvector 是下一阶段重点，但在前端和持久化完成前直接做，会让项目复杂度跳太快。

## 10. 当前已知限制

1. 支持 `.txt`、`.md` 和可提取文本的 `.pdf`，但不支持 DOCX。
2. 扫描版 PDF 暂无 OCR。
3. 检索还不是向量检索。
4. 没有用户登录。
5. 没有工单系统。
6. 没有 Agentic RAG。
7. 没有 GraphRAG。
8. 没有 tracing/eval 面板。
9. 前端没有做复杂错误恢复，只做了基础错误提示。

## 11. 下一步推荐任务

推荐优先级：

### 下一步 1：前端实际联调与体验修复

目标：

```text
用户用浏览器打开前端，完成上传、查看列表、提问、切换 local/api/auto。
```

要检查：

- 前端能否成功加载文档列表。
- 上传后列表是否刷新。
- local 模式是否能回答。
- api 模式是否能调用 DeepSeek。
- sources 是否展示正确。
- 页面在小屏幕是否可用。

### 下一步 2：接入 embedding

目标：

```text
把当前关键词检索升级成语义检索。
```

推荐路线：

1. 已完成 Retriever 接口和 keyword retriever。
2. 新增 embedding 生成函数。
3. 新增 embedding retriever。
4. 后续把 SQLite 升级为 PostgreSQL + pgvector。

### 下一步 3：开始 V2 Agentic RAG

V2 要做：

- 问题分类。
- query 改写。
- 多轮检索。
- 检索结果评分。
- 无证据拒答。
- 回答前检查引用。

## 12. 新对话接续提示

如果开启新对话，可以把下面这段给 AI：

```text
我正在做“企业智能工单与知识助手平台”，路径是 D:\multi agents。

这是一个面向企业知识问答、工单处理和风险分析的 AI 项目。长期目标包括 RAG、Agentic RAG、GraphRAG、MCP 工具调用、多 Agent、人工审批、tracing/eval 和 token 成本监控。

当前处于 V1：知识库问答系统。

已经完成：
1. FastAPI 后端。
2. txt/md 文档上传。
3. PDF 文档上传和文本提取，支持 PyMuPDF / pypdf 兜底。
4. 文档切块。
5. SQLite 持久化保存 documents 和 chunks。
6. GET /documents 文档列表。
7. DELETE /documents/{document_id} 删除文档。
8. POST /chat 提问。
9. answer_mode 支持 local/api/auto。
10. local 模式包含延期原因规则式因果抽取。
11. api 模式调用 DeepSeek / OpenAI 兼容 API。
12. React/Vite 前端工作台，支持上传、列表、删除、提问、模式选择、回答、来源和执行轨迹展示。

关键文件：
- apps/api/app/main.py
- apps/api/app/rag.py
- apps/api/app/database.py
- apps/api/app/llm.py
- apps/api/app/config.py
- apps/api/app/models.py
- apps/web/src/main.tsx
- apps/web/src/api.ts
- apps/web/src/styles.css
- docs/session-handoff-2026-06-29.md
- docs/troubleshooting-log.md

启动方式：
后端：
cd "D:\multi agents\apps\api"
uvicorn app.main:app --reload --port 8000

前端：
cd "D:\multi agents\apps\web"
npm run dev

后续请优先帮助我做前端联调体验修复，然后再做 embedding 检索、Agentic RAG。
```
