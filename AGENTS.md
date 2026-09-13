# Project Agent Instructions

本仓库是 Enterprise Insight Platform 的唯一交付仓库。

## 启动要求

1. 维护或扩展本项目时，读取并遵循仓库版 Skill：
   `skills/enterprise-insight-maintainer/SKILL.md`，不依赖其他机器上的用户目录。
2. 读取 `knowledge/INDEX.md`，再按任务加载相关知识文档。首次接手先读 `docs/START_HERE.md`；可用 `quality/agent-evals/context-harness.ps1 -Mode brief` 恢复入口，并核对 Git 状态。
3. 涉及业务定位、服务边界、身份模型、事件语义、数据所有权或交付范围的多种合理方案时，暂停并向用户确认，不自行改变已批准路线。

## 不变量

- 一个产品、一个仓库、两个后端服务、一个统一前端。
- Media Service 负责媒体生命周期；Agent Service 负责知识与分析生命周期。
- 真实 JWT/owner/tenant 隔离必须贯穿两个服务，禁止回退为自报角色头。
- 视频和文档结论必须保留可验证证据；视频证据需能定位到时间段。
- 写操作、知识发布和 PRD 发布遵循人工审批与审计。
- 原始仓库只作为迁移来源，不在整合期间反向修改。

## 完成变更前

- 运行与改动范围相称的测试。
- 运行知识库更新器，并确认漂移检查通过。
- 更新相应契约、ADR、质量证据与当前状态。
- 交接状态写回现有 `knowledge/` 与相关计划；生成文件只通过更新器生成。历史评测数字保留日期，当前验证以 `knowledge/QUALITY.md` 最新条目为准。
