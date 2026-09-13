# Nexus 参考站复核与补齐记录

日期：2026-09-13。复核基线：`main@9c713be`。目标是核对公开参考机制、已批准方案与实际调用链，补齐方案内遗漏，并验证本机产品；保留现有模型、Media/Agent 边界、JWT scope 和审批语义。

## 参考范围

有效入口为 [项目介绍与核心价值](https://javaup.chat/super-agent/overview/project-intro/)，目录根地址 `/super-agent/` 本次返回 403。文章侧栏共有 **88 页**，公开 HTML 均返回 200：**17 页无付费提示，71 页仅开放预览**。17 页包括目录、部署说明等，不能表述成 17 篇完整技术实现。此前“7 页概览 + 25 页细节”的记录已过时。

| 目录类别 | 页数 |
| --- | ---: |
| 概览、Pro 概览与 Harness | 10 |
| 启动与使用 | 7 |
| 功能导览 | 10 |
| 文档解析 / 索引构建 | 5 / 4 |
| 对话架构 / SSE 与流生命周期 | 2 / 2 |
| 执行前准备链 | 21 |
| 检索与对话执行器 | 14 |
| 图谱执行器 / ReAct 执行器 | 6 / 7 |

只阅读公开正文与付费提示之前的预览，没有访问付费正文。主页还公开链接了 [开源仓库](https://github.com/java-up-up/nexus-agent)，但本轮 GitHub API 返回限流 403，浏览器连接关闭，未取得该仓库源码，因此不声称审查了 Nexus 完整源码或 Pro 实现。公开抓取清单保存在忽略目录 `runtime/codex-reference-audit/inventory.json`；下列结论是本项目自己的对照记录。

## 机制到实现的逐项对照

| 参考机制 | 本项目核对结果与实现入口 |
| --- | --- |
| [准备链与执行器分流](https://javaup.chat/super-agent/feature-guide/preparation-orchestrator/) | `architecture/planning.py` 固化 ExecutionPlan，`architecture/orchestration.py` 注册 clarify / retrieval / agentic / tool_only；沿用已批准模式与确定性降级。 |
| [记忆、改写与主题路由](https://javaup.chat/super-agent/feature-guide/conversation-memory/) | `conversation_memory.py`、`topic_routing.py`：窗口/摘要、有界字面指代补全、授权候选置信度。记忆只提示主题，每轮重新取证。没有把历史回答当新事实。 |
| [会话工程机制](https://javaup.chat/super-agent/overview/core-architecture/) | 数据库租约、CAS fencing、取消清理；模型/工具每请求 8/6、每会话 40/30。使用现有数据库实现租约，并未为了复刻参考站另加 Redis 依赖。 |
| [通道过滤与融合](https://javaup.chat/super-agent/chat-executors/channel-retrieval-rrf/) | **本轮补齐**：授权快照 → 各通道过滤 → 真实语义通道 RRF（K=60）。关键词相对阈值 0.35；语义/哈希分数下限 45/10，均可通过 Settings 配置。哈希降级保留关键词优先，不伪装成独立语义投票。 |
| [精排与最终 Top-K](https://javaup.chat/super-agent/chat-executors/channel-retrieval-rerank/) | **本轮修复**：`selection_rank` 独立于 `score`，standard、agentic、多轮去重和分析快照均保留最终顺序；可选 Top-12 精排发生在最终选择之前。畸形分数、异常、超时会保留先前顺序并记录原因。 |
| [父子块与证据预算](https://javaup.chat/super-agent/chat-executors/final-topk-and-summary/) | `evidence_sources.py`、`evidence_budget.py`：按最终排名取 4 个锚点，再扩展同文档同章节的授权相邻块，单来源 2200、总量 5200 字符。视频保持原段落/时间范围。这里精排的是命中子块；章节扩展发生在选择之后，没有照搬 Pro 的整父块/结构树精排。 |
| [通道与文档观测](https://javaup.chat/super-agent/chat-executors/trace-channel-observations/) | **本轮补齐**：各通道原始数、过滤后数、最终保留锚点数、阈值、耗时、embedding/fusion 状态；精排失败原因。JSON/SSE 共用 trace，并由现有聊天日志持久化。来源继续保留文档/块、相关性与视频定位。 |
| [流式输出与推荐追问](https://javaup.chat/super-agent/chat-system-architecture/end-to-end-flow/) | JSON/SSE 共用 `chat_service.py`，`done` 才是最终回答。**本轮补齐** `follow_up.py`：根据本轮已授权、预算后的证据生成最多 3 个规则追问，携带明确主题、跳过当前及最近四轮同主题已问意图；拒答不推荐。独立提问不使用历史，未增加模型调用。 |
| [文档生命周期](https://javaup.chat/super-agent/feature-guide/document-lifecycle/) | 支持 txt/md/PDF 文本解析、结构切块、双格式向量、后台补齐；视频由 Media 管理。批准知识另有版本、替代/撤回与历史引用状态，不混同普通上传。 |
| [图谱与受控工具](https://javaup.chat/super-agent/feature-guide/graph-query-and-tool-calling/) | 已有 SQLite 确定性图谱与授权遍历，工具走白名单、预算、审批与审计。图谱是辅助上下文，没有宣称完成 Pro 五通道统一检索或开放式联网 Agent。 |
| [提示词、观测与 Harness](https://javaup.chat/super-agent/overview/ai-harness-refactoring/) | 外置 Prompt、阶段计时、影子路由、反馈与失败回放；仓库 Skill、启动 harness、人工知识源、增量路由索引与 CI 漂移门禁均保留。**本轮修正** Recall@3 的统计窗口和 hybrid 决策门禁。 |
| [Java/Python 工程边界](https://javaup.chat/super-agent/overview/engineering-practice/) | 参考 Pro 用 Java 主链路 + Python 工具；本项目按已批准产品职责采用 Media Spring + Agent FastAPI + React。无需改写业务所有权来匹配参考项目的语言分工。 |

## 本轮确认并修复的遗漏

1. **精排结果没有真正进入答案**：回答层再次按原始分数/标题排序，能把精排第一名挤出 Top-K。现以检索最终名次选择证据，标题先验移至融合之前；相关性门控仍使用实际分数。
2. **弱命中重复获票**：正分即参加 RRF，没有落实独立质量过滤。现先过滤各通道，仅接受的信号参与融合与相关性计分。
3. **哈希降级误当语义证据**：取消下游重排后，哈希碰撞曾挤掉准确的合同编号与交付日期来源。现 `keyword_then_hash` 优先保留合格关键词候选，哈希独有候选补充在后；真实语义结果仍用 RRF。
4. **通道失败拖垮整个请求**：每请求创建线程池，异常不隔离，也没有有效截止期限。现每进程每通道默认 4 个在途任务，无额外排队额度；默认通道 2 秒、精排 3 秒，超时不等待线程退出，满员立即降级。取消和租约 guard 传到 worker；迟到结果不能回写答案。
5. **畸形精排输出与重试证据丢失**：短数组、NaN/Inf 等会造成异常或虚假的 applied 状态；重试高分替换会丢掉旧 query。现验证长度/有限值并保留最佳排名、最高相关性及完整 query 并集。
6. **用户提示与统计失真**：有库但无合格证据不再报“请先上传”，通道全失败单独提示暂不可用；指标依据失败阶段识别拒答。固定追问改为本轮证据支持的主题建议，JSON/SSE 一致。
7. **质量门禁遗漏**：Recall@3 原来检查了全部最多 4 个来源，且决策阈值只检查 keyword。现严格检查前三条，并同时检查 hybrid 决策；新增 3 条排序黄金题和 2 条追问场景。
8. **浏览器连续追问重复推荐**：最初只跳过当前问题，会出现“延期原因 → 负责人 → 又推荐延期原因”。现复用授权记忆，跳过最近四轮同一明确主题集合中已经问过的意图；不拿历史答案或模型摘要做去重依据，不屏蔽其他主题或独立提问。追加 3 个会话场景，并验证 JSON/SSE 一致。

以上通过端到端来源选择、预算裁剪、分析冻结、故障/超时/饱和/取消、SSE 与评测口径回归验证，详见 [ADR-0019](../knowledge/decisions/0019-retrieval-ranking-and-channel-isolation.md) 和 [最新质量证据](../knowledge/QUALITY.md)。

## 明确保留的范围差异

- 沿用现有双通道检索与 SQLite 图谱，不引入 PGVector、ES、Neo4j、Kafka、RAPTOR 或图社区算法。
- PDF 当前提取文本；没有结构化表格单元格问答、OCR、bbox/版面引用、Document Mind 云解析或跨格式复杂解析路由。这些需要独立数据、权限和质量标准，不属于原优化阶段漏交。
- 会话改写和追问推荐均受限于当前证据/规则，不等同于 Pro 的任意模型改写、完整多子问题独立预算或语义引用修复。
- 没有新增 MCP、Tavily 或开放式工具循环；写操作保持既有审批与审计。
- 真实 BGE/reranker、外部 LLM、生产容量和多实例故障需部署环境补证。本轮用 hash/local 模式验证工程链路，未调整现有模型选择。

## 验证与交接

代码门禁：最终 Agent **271/271**、会话专项 **25/25**、Media **150/150**（JDK 17.0.18）、Web **26/26**；Python lint 通过，Web lint 0 error / 10 warnings，构建通过。V6 45 题，hybrid 决策 **44/45**、真实 Recall@3 与事实覆盖均 **39/40**；PRD **12/12**、生命周期、V5 通过；Conversation 最终 **14/14**。这些是小型闭集回归，不是开放域准确率。

检索补齐提交 `ee51a8e`、浏览器追问补丁 `acb1d7e` 已部署，当前入口为 [本机工作区](http://127.0.0.1:8080)。最终实际业务链 **42/42**、同源 **5/5**、浏览器两轮问答/去重与 1280/390px 布局通过。当前 Agent 镜像为 `release-acb1d7e` / `a6180c2959a9`，Web/Media 沿用原镜像；在线备份、八个表原行保留与恢复位置见 [运维记录](../knowledge/OPERATIONS.md)，完整日志见 [质量记录](../knowledge/QUALITY.md)。原阶段 0–4 和两次发布材料按日期保留。
