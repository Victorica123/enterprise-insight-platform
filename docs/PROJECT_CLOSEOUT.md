# Enterprise Insight Platform 项目收尾基线

- 状态：面试交付基线持续维护，按已批准范围精简实现与阅读入口
- 日期：2026-08-30 封板；2026-09-13 架构优化与本机部署；2026-09-14 面试文档合并；2026-09-15 LangGraph 首阶段接入
- 框架范围：六阶段由 LangGraph 调度，继续复用业务检查点；应用说明与取舍统一维护于 ADR-0020。
- 发布口径：可本地复现的工程型试点，不是生产发布

## 收尾结论

当前围绕同一条业务主线学习、演示和维护，优先降低理解与维护成本：

> 视频/文档 → 授权证据 → 六阶段分析与等待恢复 → PRD 人工发布 → 知识独立批准并进入未来 RAG → 错误知识替代/撤回与历史审计 → 行动项审批后创建工单。

当前按已批准范围维护工程型试点。六阶段框架接入已落在源码；specialist 卡死截止/队列容量、严格引用与事实审核、真实模型独立留出集等缺口仍未补齐，也未扩大生产发布范围。

### 2026-09-15 当前交接：六阶段接入与新手入口

从报告提交 `5b48f7d` 继续落实 ADR-0020 的首阶段：六节点 `_AnalysisState` / `StateGraph` 保留在 [analysis_pipeline.py](../services/agent-service/app/analysis_pipeline.py)，替换原 `_run_initial_stages` / `_finish_analysis` 手工调度。公开 Python 入口与 HTTP 契约保持兼容；缺信息时结束本次图调用，确认请求保留冻结证据与阶段 1–4，从收敛节点继续。业务状态仍由 `analysis_store.py` 和恢复令牌 CAS 管理，没有新增框架状态库或原生 `interrupt`。

仅缓存图拓扑，每次请求建立独立状态；实际调用显式关闭 LangSmith 追踪。`langgraph==1.2.11` 及其间接依赖进入项目锁文件，Docker/CI 使用同一约束。此次优化统一编排约定和学习入口，不声称代码行数或依赖总量减少，也不把规则 specialist 说成模型专家。

[从一个例子理解项目](START_HERE.md) 成为统一新手入口，按审计报表需求讲解页面、服务和数据流，再分出核心学习内容与可选基础设施。面试指南只保留答辩与源码依据，完整框架比较仍由 [ADR-0020](../knowledge/decisions/0020-langgraph-application-report.md) 维护。最新验证统一查 [QUALITY](../knowledge/QUALITY.md)；本次没有部署已有容器，当前运行版本与恢复材料查 [OPERATIONS](../knowledge/OPERATIONS.md)。下一步按新手入口实走一条分析请求，再按需要处理独立记录的可靠性与质量缺口。

### 2026-09-15 应用报告交接（先前记录）

以 `5c136b4` 为代码基线完成 LangGraph 应用与比较报告。[ADR-0020](../knowledge/decisions/0020-langgraph-application-report.md) 同时承担报告和决策记录，涵盖源码映射、条件图、独立示例、框架比较及验收；面试指南收缩为口述与报告入口。当次只完成设计与独立示例，未迁移应用、修改依赖或部署。后续首阶段实施见上方当前交接，原验证记录保留在 [QUALITY](../knowledge/QUALITY.md)。

### 2026-09-14 文档合并交接

参考站补齐和追问修复已在 2026-09-13 提交、部署并同步至 GitHub；本次文档整理的应用基线为 `c779ce6`，原部署和恢复材料见 [OPERATIONS](../knowledge/OPERATIONS.md)。下方各批次数字与“未推送”等描述保留其历史时点，不代表当前状态。

四份面试材料合并为 [讲解与技术答辩](INTERVIEW_GUIDE.md) 和 [演示与计时练习](DEMO_SCRIPT.md)：前者维护选型、六类技术问题、代码证据、工程故事与贡献边界，后者维护现场步骤。旧稿由 Git 历史保留。已澄清自研有限编排、规则 specialist、异常与卡死差别、轻量 Reviewer 以及 Hit@3/事实子串命中口径；验收结果与剩余工作写入 [QUALITY](../knowledge/QUALITY.md)。

### 2026-09-04 状态补充

在上述封板基线之上，本轮生产试点加固已完成并通过本机回归：Agent Service 154/154、Media Service 在 Temurin JDK 18.0.2.1 下 131/131、Web TypeScript/Vite 构建通过，localhost-only 纵向验收保持 33/33。新增的 MySQL/RS256/OIDC/保留期/模型出境门禁仍属于准生产路径；当前主机没有 Docker、k6 和经批准的外部模型凭证，因此真实中间件、容量、故障注入和生产 SLO 仍未形成通过证据。本文后续历史数字保留其对应日期，最新可审计数字以 [`knowledge/QUALITY.md`](../knowledge/QUALITY.md) 为准。

### 2026-09-11 状态补充

2026-09-01 至 09-10 的准生产基线工作已全部提交入库，Git 历史不再停留在 2026-08-31。新增 ruff 与 ESLint 门禁进入 CI；收尾回归中发现并修复两处缺陷：ruff 自动修复删除了 `graph_store` 的透传导入导致 Agent 服务无法加载，以及 PRD 门禁在没有本地 BGE 模型的环境里因 hybrid RRF 平局排序错误而失败。当前口径：Agent 158/158、Media 在 JDK 17 与 18 下 135/135、Web lint 0 error 与 7/7 单测、localhost-only 验收 33/33；`compose.local.yml` 三容器在本机 Docker 中健康运行。生产边界不变，细节见 `knowledge/QUALITY.md` 2026-09-11 条目。

### 2026-09-13 架构优化接手完成

用户批准的阶段 0–4 已完成并提交为 `af2dc6e`。Agent 244/244、Media 150/150、当时 Web 21/21 和全部相关 Agent 门禁通过；H2/SQLite 与真实 MySQL/Redis/RocketMQ/MinIO 各 42/42。新增 Media 职责/配置拆分、Flyway/阶段记录/熔断，以及 Web Router/Query/会话与角色隔离。MySQL 新旧库迁移、断连恢复、两库备份还原和有限 k6 通过；仍不宣称外部 AI、Keycloak/RS256、生产容量或完整灾备已验收。下方交付清单继续适用，旧日期保留历史；当前证据以 `knowledge/QUALITY.md` 最新条目为准。

### 2026-09-13 本机发布完成

入口 **http://127.0.0.1:8080** 已更新，`enterprise-insight-local` 三容器均 healthy。发布浏览器验收补齐了 nginx 同源端口修复 `daa29bf` 与播放代理前缀修复 `03f810b`，Web 最终 **26/26**；实际入口带 Origin 的 **42/42** 业务验收及 **5/5** 同源检查通过。真实登录、3 秒视频播放/206、五个阶段、SSE 证据回放与六路由宽窄屏已实走。

升级前备份 `backups/local-release-20260913-132509/pre-upgrade.zip` 的 516 文件校验通过；数据副本与实际库迁移均保留原表字段、行数和内容摘要，baseline 已复位 false。旧镜像和环境配置保留，正式降级回退未执行；细节见 `knowledge/OPERATIONS.md`。测试副本和浏览器已关闭，原迁移来源及 `erp-mssql` 未修改。当前仍是 H2/SQLite、HS256 与 mock/local AI 的本机交付；仓库无 remote，提交未推送。

## 已封板的交付物

| 交付物 | 入口 |
| --- | --- |
| 产品定位与主链路 | `README.md`、`knowledge/PRODUCT.md` |
| 从一个例子理解项目、核心学习与代码路线 | [新手入口](START_HERE.md) |
| 架构、数据流与技术实现 | `knowledge/ARCHITECTURE.md`、`knowledge/TECHNICAL_IMPLEMENTATION.md` |
| 面试叙事、框架取舍、连续追问、故事与贡献边界 | [讲解指南](INTERVIEW_GUIDE.md) |
| 8 分钟操作、计时练习、打断恢复与失败兜底 | [演示脚本](DEMO_SCRIPT.md) |
| 本地无服务器验收 | `scripts/local_acceptance.py`、`docs/LOCAL_RELEASE_RUNBOOK.md` |
| 测试与浏览器证据 | `knowledge/QUALITY.md`、`docs/images/interview/` |
| 长期维护入口 | `skills/enterprise-insight-maintainer/`、`knowledge/INDEX.md` |

## 封板质量证据（2026-08-30 历史基线）

- Agent Service：137/137（本轮 P0/P1 增量后）。
- Media Service：JDK 18 下 124/124。
- Agent V6：keyword、embedding、hybrid 均为 decision 98%、recall@3 97%、fact 97%。
- PRD V1：12 个手工场景的 decision、问题召回与精确率、objective Top-1、冲突、证据、支持率、验收、检查点和 specialist 顺序均为 100%；该闭集不外推真实业务效果。
- Knowledge Lifecycle V1：personal 替代、personal 撤回、team 替代三类场景的检索、版本链、历史状态、隔离、四眼、幂等、图谱和物理保留均为 100%；不外推生产容量。
- 平台：33/33 localhost-only 纵向检查。
- Web：TypeScript 与 Vite 生产构建通过。
- Web：已实现知识版本链、替代/撤回申请与审批、历史聊天失效状态展示；TypeScript 和 Vite 生产构建通过。既有浏览器截图仍只证明 Phase 1 运行，Phase 2 以自动化纵向验收为准。
- 并发迁移复测：20 并发、40 请求，40/40 返回 200。
- 维护知识：知识更新脚本会在代码/文档变更后重新生成批准来源、chunk、增量向量复用和 revision 查询缓存；Skill 校验与漂移检查必须以最后一次命令输出为准。
- P0/P1 增量：Media outbox 已增加条件 claim/lease、过期接管、旧 worker fencing 和 DEAD 退避；Agent 问答侧 Router/Planner/Tool Agent 已增加 provider-compatible 结构化 JSON，但六阶段 specialist 仍是确定性 baseline。

具体命令、环境与不能外推的边界以 `knowledge/QUALITY.md` 为准。

## 面试前最后准备

1. 提前运行 `python scripts/local_acceptance.py`，保留 PASS 输出；本地验收使用合法 MP4 `ftyp` 头，验证上传校验不会被测试字节绕过。
2. 按 [讲解指南](INTERVIEW_GUIDE.md) 准备口述与追问，再按 [演示脚本](DEMO_SCRIPT.md) 计时练习和操作。
3. 熟练讲出三个故事：业务闭环、并发迁移缺陷修复、两后端与授权缓存的架构取舍。
4. 明确个人贡献，区分原媒体能力、迁移整合与新增 Agent/知识治理能力。
5. 主动说明 localhost/mock 证明的是工程链路，不代表生产吞吐、真实模型质量或业务 ROI。

## 冻结与重新打开规则

封板后只在以下情况重新进入开发：

- 自动化测试、演示主链路或安全边界出现可复现缺陷；
- 真实面试反馈暴露无法回答或无法演示的核心缺口；
- 用户明确批准既有能力的精简或编排替换，并保留证据、权限与审批契约；
- 用户批准进入生产化阶段，并明确 IdP、撤权、数据保留、外部模型策略和目标 SLO；
- 代表性数据证明当前 SQLite 检索、进程级缓存或媒体处理能力已经超过预算。

Agent 编号迁移、Media Flyway 和本机中间件/备份恢复已有验证；剩余生产路线是目标 IdP/即时撤权、目标库升级/回退、长时与多实例故障、Prometheus/OTel 告警、异机灾备和业务 ROI。领域任务卡死保护、严格事实审核与真实模型评测是另行记录的实现/质量缺口，不因封板而声称已解决。

## 维护要求

后续任何修改继续通过 `enterprise-insight-maintainer` Skill，更新相应契约、ADR、质量证据和语义知识索引。禁止为了简历数字静默修改验证结果，也禁止把候选 SLO、mock 模型或单机延迟包装成生产事实。
