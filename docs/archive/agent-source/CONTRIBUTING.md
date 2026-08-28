# 贡献指南

## 开发环境

- Python 3.10+、Node 18+
- 后端：`cd apps/api && pip install -r requirements.txt`（语义 embedding 可选装 `requirements-embedding.txt`）
- 前端：`cd apps/web && npm install`

本地跑起来：后端 `uvicorn app.main:app --reload --port 8000`，前端 `npm run dev`，
演示数据 `python scripts/seed_demo.py`。详见 [README](README.md)。

## 提交前必须通过的检查

CI（`.github/workflows/ci.yml`）会执行同样的内容，建议本地先跑：

```bash
# 1. 回归测试（离线确定性，不消耗 API 额度）
cd apps/api
LLM_ROUTER_ENABLED=0 python -m pytest tests -q

# 2. 五道评测门禁（防优化回退）
cd ..
python scripts/evaluate_v2.py   # 依次到 evaluate_v6
```

门禁不通过时不要调阈值"让它过"——阈值变更需要在 PR 里说明实测数据与理由
（墙钟类阈值的历史校准见 README「测试与评测门禁」）。

## 改动指引

| 改什么 | 入口 | 注意 |
| --- | --- | --- |
| 新端点 | `app/routes/` 新建或扩展路由 | 鉴权走 `app/auth.py` 的 `require_*`；端点保持薄，业务放领域层 |
| 新工具 | `app/tools.py` 注册表 | 声明 JSON Schema（参数校验/白名单自动生效）；写操作配 `approved_handler` |
| 检索策略 | `app/retrievers.py` | 实现 Retriever 协议并注册到 `get_retriever` |
| 图谱抽取 | `app/graph_store.py` | 保持增量抽取 + 删除自动重建的原子性 |
| LLM 提示词 | `app/llm.py` / `app/llm_router.py` | 必须保留规则降级通道；失败要记日志 |
| 前端面板 | `apps/web/src/features/` | API 调用统一走 `src/api.ts`，带角色头 |

## 项目约定

- **测试是回归契约**：修复缺陷时在 `tests/` 补一个绑定该缺陷的用例（参考 `test_p0_hardening.py` 的注释风格）。
- **评测门禁是质量底线**：改动检索/证据门控/图谱抽取后，跑一遍 V2/V4/V6 门禁对比基线。
- **安全默认值**：新端点默认最小权限；异常原文不进用户可见响应，只进服务端日志。
- **日志留痕**：任何降级路径（LLM 回退、模型不可用、审批拒绝）都要有 warning 级日志。
- 注释密度对齐现有代码：讲清楚"为什么"，不复述"做什么"。

## 提交信息

格式：`类型: 摘要`，类型常用 feat / fix / docs / test / refactor / chore。
多行正文说明动机与影响，参考 `git log` 中的现有提交。
