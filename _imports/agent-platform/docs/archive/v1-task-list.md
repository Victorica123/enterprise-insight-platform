# V1 开发任务清单

这份清单用于指导 V1 从学习版逐步升级到真实 RAG 版本。

## 当前已完成

- 创建项目根 README。
- 创建 V1 学习说明。
- 创建 FastAPI 后端目录。
- 实现 `GET /health` 健康检查接口。
- 实现 `POST /documents` 文档上传接口。
- 支持 `.txt`、`.md` 和 `.pdf` 文档。
- 实现简单文档切块。
- 使用 SQLite 持久化保存 document 和 chunk。
- 实现 `GET /documents` 文档列表接口。
- 实现 `DELETE /documents/{document_id}` 文档删除接口。
- 实现 `POST /chat` 提问接口。
- 使用关键词重叠检索相关 chunk。
- 返回模板答案和来源。
- 支持延期原因类问题的规则式因果抽取。
- 支持可选 DeepSeek / OpenAI 兼容 API，让大模型基于来源回答。
- `POST /chat` 支持 `answer_mode`，可选择 `local` / `api` / `auto`。
- 新增 React 前端工作台，支持上传、文档列表、提问、模式选择和来源展示。
- 前端文档列表支持删除文档。
- 后端支持 PDF 文本提取，优先使用 PyMuPDF，可回退到 pypdf。
- `/chat` 返回执行轨迹 trace。
- 前端展示执行轨迹，包括检索、来源选择和回答路径。
- V2-lite：新增本地 query 扩展，trace 中展示扩展 query。
- V2-lite：新增 evidence_check，证据不足时拒答并写入 trace。
- 在 `docs/troubleshooting-log.md` 记录 evidence_check 证据门控设计和面试表达。
- 新增 `apps/api/app/retrievers.py`，抽象 Retriever 接口并保留 keyword retriever。
- 新增 `docs/context-brief.md` 和 `scripts/context-harness.ps1`，用于压缩上下文和减少重复读写。
- 新增本地哈希 embedding 学习版，支持 `keyword` / `embedding` / `hybrid` 检索模式切换。
- 新增 embedding 状态接口和重建接口，前端支持查看向量覆盖率并一键重建。
- 新增 `/system/status` 和前端状态面板，展示 API、文档、chunk、LLM 和 embedding 状态。
- 前端补齐复制回答、清空回答、关闭错误提示、刷新工作台等 V1 交互。

## 下一步任务 1：本地启动 API

目标：

```text
能在浏览器打开 FastAPI Swagger 页面。
```

命令：

```bash
cd apps/api
pip install -r requirements.txt
uvicorn app.main:app --reload --port 8000
```

打开：

```text
http://127.0.0.1:8000/docs
```

验收标准：

- `/health` 返回 `{"status": "ok"}`。
- Swagger 页面能看到 `/documents` 和 `/chat`。

## 下一步任务 2：手动测试上传和提问

先准备一个 `sample.md`：

```md
# 客户 A 项目记录

客户 A 的项目原计划在 2026 年 6 月 20 日交付。
由于测试环境部署延迟，项目交付时间推迟到 2026 年 7 月 5 日。
项目负责人是张三。
合同中约定，如果延期超过 15 天，需要向客户提交风险说明。
```

测试流程：

1. 在 Swagger 页面调用 `POST /documents` 上传 `sample.md`。
2. 调用 `POST /chat` 提问：

```json
{
  "question": "客户 A 的项目为什么延期？"
}
```

验收标准：

- 返回答案中能看到相关文档内容。
- `sources` 中包含 `filename`、`chunk_index`、`score`、`content`。

## 下一步任务 3：接入真实大模型

目标：

```text
把模板回答替换为大模型基于来源生成回答。
```

需要新增：

- 环境变量 `OPENAI_API_KEY`。
- LLM 客户端封装。
- prompt 模板。
- 错误处理。

当前已经完成基础封装：

- `app/llm.py` 负责调用大模型。
- 默认支持 DeepSeek API，兼容 OpenAI SDK。
- 如果没有配置 API Key，系统会继续使用模板答案。
- 如果大模型调用失败，系统会返回模板答案和错误说明。
- 用户可以通过 `answer_mode` 选择回答模式。

PowerShell 配置示例：

```powershell
python -m pip install -r requirements.txt -i https://pypi.tuna.tsinghua.edu.cn/simple
Copy-Item .env.example .env
```

`.env` 示例：

```text
LLM_PROVIDER=deepseek
DEEPSEEK_BASE_URL=https://api.deepseek.com
DEEPSEEK_MODEL=deepseek-v4-flash
DEEPSEEK_API_KEY=你的 DeepSeek API Key
DEFAULT_ANSWER_MODE=local
```

`POST /chat` 请求示例：

```json
{
  "question": "请总结客户 A 项目风险",
  "answer_mode": "api"
}
```

输入给模型的内容应该包含：

```text
系统角色：你是企业知识库助手，只能基于给定来源回答。
用户问题：...
检索来源：...
输出要求：答案必须引用来源，如果资料不足要明确说不知道。
```

验收标准：

- 回答更自然。
- 回答不编造未出现在来源中的信息。
- 当来源不足时，会拒答或说明资料不足。

## 已完成升级：SQLite 持久化

目标：

```text
上传文档后保存到数据库，服务重启后文档和 chunk 不丢失。
```

已完成：

- 新增 `app/database.py`。
- 自动创建 SQLite 数据库。
- 新增 `documents` 表。
- 新增 `chunks` 表。
- 上传文档时写入数据库。
- 提问时从数据库读取 chunk 进行检索。
- 新增 `GET /documents` 文档列表接口。
- 新增 `DELETE /documents/{document_id}` 文档删除接口。
- 前端支持删除文档并自动刷新列表。

数据库位置：

```text
apps/api/data/knowledge_base.sqlite3
```

## 已完成升级：PDF 上传支持

目标：

```text
用户可以上传 PDF，后端提取文本后进入同一套 RAG 流程。
```

已完成：

- 新增 `app/document_parser.py`。
- `.txt` / `.md` 使用 UTF-8 文本解析。
- `.pdf` 优先使用 PyMuPDF 提取每页文本。
- 如果 PyMuPDF 未安装，回退到 pypdf。
- 上传接口支持 `.pdf`。
- 前端文件选择支持 `.pdf`。
- 生成中文 PDF 测试样本 `docs/sample-project-delay-cn.pdf`。
- 优化中文 PDF 抽取文本的换行、字段和 Unicode 清洗。

注意：

- 扫描版 PDF 如果没有 OCR 文本层，可能无法提取内容。
- 加密 PDF 或损坏 PDF 会返回解析失败。
- 中文 PDF 需要字体本身支持可提取文字层；本项目测试样本使用系统字体 `NotoSansSC-VF.ttf`。

## 下一步任务 4：接入 embedding 和 pgvector

目标：

```text
把关键词检索替换成向量相似度检索。
```

需要新增：

- PostgreSQL 数据库。
- pgvector 插件。
- documents 表和 chunks 表升级。
- embedding 字段。
- embedding 生成逻辑。
- 相似度查询。

当前进度：

- 已完成 Retriever 接口和 keyword retriever 拆分。
- 下一步优先新增 `EmbeddingRetriever`，再决定 SQLite 过渡方案或直接升级 PostgreSQL + pgvector。

建议表结构：

```sql
create table documents (
  id uuid primary key,
  filename text not null,
  created_at timestamptz not null default now()
);

create table chunks (
  id uuid primary key,
  document_id uuid not null references documents(id),
  chunk_index int not null,
  content text not null,
  embedding vector(1536),
  created_at timestamptz not null default now()
);
```

验收标准：

- 服务重启后文档不会丢失。
- 检索结果比关键词方式更稳定。
- 可以根据语义相似度找到相关内容。

## 下一步任务 5：增加前端页面

目标：

```text
提供一个简单可演示的 Web 页面。
```

页面包括：

- 文档上传区域。
- 已上传文档列表。
- 聊天输入框。
- 答案展示区。
- 来源展示区。

验收标准：

- 不需要使用 Swagger 也能完成上传和提问。
- 面试或录屏时可以直接演示。

## V1 完成标准

V1 完成时，系统应该做到：

- 可以上传企业资料。
- 可以把资料切块并保存。
- 可以基于用户问题检索相关资料。
- 可以用大模型基于资料回答。
- 可以展示来源引用。
- 可以通过前端完成完整演示。
- 可以查看一次问答的执行轨迹。

当前 V1 已收口。后续进入 V2：Agentic RAG，或先接真实 embedding / pgvector。
