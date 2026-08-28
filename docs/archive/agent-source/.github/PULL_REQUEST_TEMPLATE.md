## 变更说明

<!-- 做了什么、为什么做。关联 Issue 请写 Fixes #N -->

## 变更类型

- [ ] feat：新功能
- [ ] fix：缺陷修复
- [ ] docs：文档
- [ ] test：测试
- [ ] refactor / chore

## 提交前检查（CI 会执行同样内容）

```bash
cd apps/api && LLM_ROUTER_ENABLED=0 python -m pytest tests -q
python scripts/evaluate_v2.py  # 到 evaluate_v6
cd ../web && npm run build
```

- [ ] 87 个回归测试通过
- [ ] 评测门禁通过（若调整了阈值，已在下方说明实测数据与理由）
- [ ] 新端点已按最小权限接入 `app/auth.py` 鉴权
- [ ] 新降级路径有 warning 日志，异常原文不进用户可见响应
