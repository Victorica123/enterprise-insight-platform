# API 服务（FastAPI）

企业智能工单与知识助手平台的后端。完整功能说明与快速开始见[仓库根 README](../../README.md)。

## 本地开发

```bash
cd apps/api
pip install -r requirements.txt          # 基础依赖（零配置可跑，无需 API Key）
# 可选：真实语义 embedding（fastembed/BGE-small-zh，本地 ONNX）
pip install -r requirements-embedding.txt

uvicorn app.main:app --reload --port 8000
```

- API 交互文档：<http://127.0.0.1:8000/docs>
- 数据库自动创建于 `apps/api/data/knowledge_base.sqlite3`（已 gitignore）

## 配置

复制 `.env.example` 为 `.env` 按需修改。常用项：

- `DEEPSEEK_API_KEY` / `OPENAI_API_KEY`：接入真实 LLM（配合 `DEFAULT_ANSWER_MODE=api|auto`）
- `EMBEDDING_MODEL`：真实语义 embedding（未安装依赖时自动降级哈希向量）
- `LLM_ROUTER_ENABLED=0`：关闭 LLM 路由，走纯规则版（测试/CI 默认）
- `APPROVAL_SOD_ENFORCED=0`：关闭审批职责分离（四眼审批）

## 测试

```bash
LLM_ROUTER_ENABLED=0 python -m pytest tests -q    # 87 个回归测试
python ../scripts/evaluate_v2.py                  # V2~V6 离线评测门禁
```

## 模块地图

| 模块 | 职责 |
| --- | --- |
| `routes/` | HTTP 端点（chat / documents / tickets / graph / observability / embeddings） |
| `agentic_rag.py` | Agentic 编排：Router → Planner → Retriever → Graph → Tool → Reviewer，trace 全程记录 |
| `rag.py` | 标准 RAG、证据门控（分数/意图覆盖/主题锚点）、引用审核 |
| `retrievers.py` | keyword / embedding / hybrid（RRF 融合）三种检索 |
| `graph_store.py` / `graph_rag.py` | SQLite 图存储、规则抽取、BFS 关系链（学习版 GraphRAG） |
| `ticket_store.py` | 工单 / 审批 / 工具审计：原子抢占、幂等键、TTL、exact-once 指标 |
| `tools.py` | 受控工具注册表：参数校验、白名单、审批草稿 |
| `llm_router.py` / `llm_client.py` | LLM 路由/规划/工具选择（规则版降级）；共享超时/重试/预算的客户端 |
| `slot_extraction.py` | 工具槽位抽取（标题/优先级/工单 ID/目标状态，模糊即拒绝） |
| `logging_config.py` | JSON 结构化日志 |

鉴权约定：所有端点接受 `X-User-Role`（viewer/operator/admin，默认 viewer）；
写操作与审计数据端点要求 operator+；`X-User-Id` 用于审批职责分离。策略集中在 `app/auth.py`。
