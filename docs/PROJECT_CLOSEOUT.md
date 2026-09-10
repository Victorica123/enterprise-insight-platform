# Enterprise Insight Platform 项目收尾基线

- 状态：面试交付基线已封板
- 日期：2026-08-30
- 发布口径：可本地复现的工程型试点，不是生产发布

## 收尾结论

当前工作内容已经足够支撑全栈软件工程师与 Agent 工程师面试，不再继续横向增加功能。产品已经形成一条可讲、可操作、可验证的主链路：

> 视频/文档 → 授权证据 → 六阶段分析与等待恢复 → PRD 人工发布 → 知识独立批准并进入未来 RAG → 错误知识替代/撤回与历史审计 → 行动项审批后创建工单。

停止继续开发的原因不是“没有优化空间”，而是剩余事项主要依赖正式业务和生产环境决策。此时继续添加向量数据库、Kubernetes、更多模型或更多页面，会扩大主线并制造无法证明的复杂度。

### 2026-09-04 状态补充

在上述封板基线之上，本轮生产试点加固已完成并通过本机回归：Agent Service 154/154、Media Service 在 Temurin JDK 18.0.2.1 下 131/131、Web TypeScript/Vite 构建通过，localhost-only 纵向验收保持 33/33。新增的 MySQL/RS256/OIDC/保留期/模型出境门禁仍属于准生产路径；当前主机没有 Docker、k6 和经批准的外部模型凭证，因此真实中间件、容量、故障注入和生产 SLO 仍未形成通过证据。本文后续历史数字保留其对应日期，最新可审计数字以 [`knowledge/QUALITY.md`](../knowledge/QUALITY.md) 为准。

### 2026-09-11 状态补充

2026-09-01 至 09-10 的准生产基线工作已全部提交入库，Git 历史不再停留在 2026-08-31。新增 ruff 与 ESLint 门禁进入 CI；收尾回归中发现并修复两处缺陷：ruff 自动修复删除了 `graph_store` 的透传导入导致 Agent 服务无法加载，以及 PRD 门禁在没有本地 BGE 模型的环境里因 hybrid RRF 平局排序错误而失败。当前口径：Agent 158/158、Media 在 JDK 17 与 18 下 135/135、Web lint 0 error 与 7/7 单测、localhost-only 验收 33/33；`compose.local.yml` 三容器在本机 Docker 中健康运行。生产边界不变，细节见 `knowledge/QUALITY.md` 2026-09-11 条目。

## 已封板的交付物

| 交付物 | 入口 |
| --- | --- |
| 产品定位与主链路 | `README.md`、`knowledge/PRODUCT.md` |
| 10 分钟理解与按症状找代码 | `docs/START_HERE.md` |
| 架构、数据流与技术实现 | `knowledge/ARCHITECTURE.md`、`knowledge/TECHNICAL_IMPLEMENTATION.md` |
| 面试叙事与高频追问 | `docs/INTERVIEW_GUIDE.md` |
| 8 分钟现场演示与失败兜底 | `docs/DEMO_SCRIPT.md` |
| 计时演练、三段故事与追问速答 | `docs/INTERVIEW_REHEARSAL.md` |
| 面试官压力评审与简历技术对照 | `docs/INTERVIEWER_STRESS_REVIEW.md` |
| 本地无服务器验收 | `scripts/local_acceptance.py`、`docs/LOCAL_RELEASE_RUNBOOK.md` |
| 测试与浏览器证据 | `knowledge/QUALITY.md`、`docs/images/interview/` |
| 长期维护入口 | `skills/enterprise-insight-maintainer/`、`knowledge/INDEX.md` |

## 封板质量证据

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
2. 按 `docs/INTERVIEW_REHEARSAL.md` 计时练习一分钟介绍、8 分钟主线和追问；现场操作细节以 `docs/DEMO_SCRIPT.md` 为准。
3. 熟练讲出三个故事：业务闭环、并发迁移缺陷修复、两后端与授权缓存的架构取舍。
4. 明确个人贡献，区分原媒体能力、迁移整合与新增 Agent/知识治理能力。
5. 主动说明 localhost/mock 证明的是工程链路，不代表生产吞吐、真实模型质量或业务 ROI。

## 冻结与重新打开规则

封板后只在以下情况重新进入开发：

- 自动化测试、演示主链路或安全边界出现可复现缺陷；
- 真实面试反馈暴露无法回答或无法演示的核心缺口；
- 用户批准进入生产化阶段，并明确 IdP、撤权、数据保留、外部模型策略和目标 SLO；
- 代表性数据证明当前 SQLite 检索、进程级缓存或媒体处理能力已经超过预算。

以下事项保持为生产化路线，不作为当前面试版本的未完成工作：正式 IdP/即时撤权、Flyway/Liquibase、统一真实中间件故障注入、Prometheus/OTel 告警、备份恢复演练、真实模型评测和业务 ROI 数据。

## 维护要求

后续任何修改继续通过 `enterprise-insight-maintainer` Skill，更新相应契约、ADR、质量证据和语义知识索引。禁止为了简历数字静默修改验证结果，也禁止把候选 SLO、mock 模型或单机延迟包装成生产事实。
