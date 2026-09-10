# ADR-0015：按架构全景建立 Agent Service 内部领域 façade

- 状态：已接受
- 日期：2026-09-05
- 范围：Agent Service 内部模块边界

## 背景

架构全景图把 Agent 系统表达为对话编排、检索与证据、执行器、知识底座、治理审批和工程护栏六层。仓库已有这些能力，但 HTTP 路由直接依赖多个大型平铺模块，调用方难以看出服务边界，继续扩展会把算法、存储和治理耦合到一起。

## 决策

新增 `app.architecture` 六类 façade，作为后续应用代码的稳定入口。façade 只组合已有实现，不在本次变更中移动数据库表、改变 HTTP/事件契约或拆分两个后端服务。旧模块和导入路径保留兼容；授权 scope、证据 provenance、审批和审计语义保持不变。

## 取舍

- 好处：路由依赖面变窄；架构图中的责任可以被代码和测试直接检查；未来替换检索或消息基础设施时有明确适配层。
- 成本：短期存在 façade 与旧实现并存，模块数量增加；需要禁止新代码绕过 façade 直接拼接跨域调用。
- 非目标：不声称已部署 PGVector、Elasticsearch、Neo4j、Redis、Kafka 或完整 MCP Runtime；不把确定性 specialist 改写成无界自治 Agent。

## 验证

`test_architecture_boundaries.py` 验证六层 manifest、principal 到 RequestContext 的 scope 传递，以及 standard/agentic 路由的调用参数。全量测试和知识漂移检查仍是交付门禁。

