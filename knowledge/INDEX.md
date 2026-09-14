# Enterprise Insight Platform Knowledge Base

本目录是项目当前事实的唯一知识入口。历史文档只用于追溯，不代表当前产品承诺。

## 阅读路由

| 需要了解 | 入口 |
| --- | --- |
| 产品定位、用户、业务闭环、范围 | [PRODUCT.md](PRODUCT.md) |
| 服务边界、数据流、运行架构 | [ARCHITECTURE.md](ARCHITECTURE.md) |
| 架构图全景与 Agent Service 六层映射 | [全景映射](../docs/ARCHITECTURE_PANORAMA.md) 与 [ADR-0015](decisions/0015-agent-service-bounded-context-facades.md) |
| 会话/SSE、主题记忆、预算、续租与取消 | [ADR-0016](decisions/0016-bounded-conversations-and-sse.md)、[AGENT_ENGINEERING.md](AGENT_ENGINEERING.md) |
| Settings、编号迁移、向量兼容与内部边界 | [ADR-0017](decisions/0017-settings-schema-and-domain-boundaries.md)、[OPERATIONS.md](OPERATIONS.md) |
| Media Flyway/阶段日志/熔断、Web Router/Query 与角色切换隔离 | [ADR-0018](decisions/0018-media-migrations-stages-and-web-queries.md)、[OPERATIONS.md](OPERATIONS.md)、[最新验收](QUALITY.md) |
| 对标 Nexus Agent 的架构优化：分阶段计划、落地记录、项目功能拆分、优化前后量化对比与取舍理由 | [优化方案与前后对比](../docs/ARCHITECTURE_OPTIMIZATION_PLAN.md) |
| Nexus 参考站最新目录、公开范围、遗漏复核、检索排名/降级与补齐证据 | [参考站复核](../docs/NEXUS_REFERENCE_AUDIT.md)、[ADR-0019](decisions/0019-retrieval-ranking-and-channel-isolation.md) |
| HTTP、事件、共享数据结构 | [CONTRACTS.md](CONTRACTS.md) 与 `../contracts/` |
| 身份、租户、权限、隐私、审批 | [DATA_AND_SECURITY.md](DATA_AND_SECURITY.md) |
| Agent 阶段、证据、评测、自进化 | [AGENT_ENGINEERING.md](AGENT_ENGINEERING.md) |
| 代码框架、完整数据流、RAG、缓存与技术讲解 | [TECHNICAL_IMPLEMENTATION.md](TECHNICAL_IMPLEMENTATION.md) |
| 测试分层、质量门禁、已验证事实 | [QUALITY.md](QUALITY.md) |
| 本地启动、配置、部署、故障恢复 | [OPERATIONS.md](OPERATIONS.md)、[本地发布手册](../docs/LOCAL_RELEASE_RUNBOOK.md)、[本机可靠性手册](../docs/LOCAL_RELIABILITY_RUNBOOK.md) 与 [SLO](../docs/SLO.md) |
| 框架选型、Agent/召回/幻觉/评测答辩、工程故事与个人贡献 | [面试讲解指南](../docs/INTERVIEW_GUIDE.md)、[自研与框架取舍](../docs/INTERVIEW_GUIDE.md#framework-choice) |
| 正式收尾、8 分钟操作、计时练习与失败兜底 | [收尾基线](../docs/PROJECT_CLOSEOUT.md)、[演示与计时脚本](../docs/DEMO_SCRIPT.md) |
| 第一次理解项目、按症状找代码 | [10 分钟项目地图](../docs/START_HERE.md) |
| 已批准且不可静默推翻的选择 | [decisions/](decisions/) |
| 从代码生成的实时结构快照 | [generated/CURRENT_STATE.md](generated/CURRENT_STATE.md) |
| 面向维护 Skill 的可再生语义路由索引 | `generated/SEMANTIC_INDEX.json`（通过脚本查询，不直接加载） |

## 维护规则

- 业务语义变化时更新对应人工文档；生成器不能替代架构判断。
- 接口或事件变化先改 `contracts/`，再改生产者、消费者和测试。
- 重要选择新增 ADR；旧 ADR 只能被新 ADR 显式取代。
- 代码、依赖、路由、测试或契约变化后执行：

```powershell
python scripts/update_knowledge.py
python scripts/update_knowledge.py --check
```

- `generated/CURRENT_STATE.md` 禁止手改。
- `generated/SEMANTIC_INDEX.json` 禁止手改；它不是真实来源，只保存内容指纹、路由 preview 和向量。
