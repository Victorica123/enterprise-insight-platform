# ADR-0008：批准知识以受治理文档进入业务检索

- 状态：已接受
- 日期：2026-08-30

## 背景

PRD 发布会生成带证据的知识候选，独立审批可以把候选从 `PENDING` 更新为 `APPROVED`。如果批准只改变状态而不进入后续检索，“知识沉淀”仍是治理记录，不是可验证的业务闭环；但让 Agent 自动改写共享知识又会绕过人工门禁并丢失来源。

## 决策

- 知识候选只有通过现有 personal OWNER 明确决定或 team 四眼决定后，才能物化为业务知识。
- Agent Service 继续拥有知识生命周期；不新增跨服务事件，也不让 Media Service 保存 PRD 或知识状态。
- 批准事务同时完成候选 compare-and-set、规范 Markdown 知识文档、hash/真实 embedding、内容 revision 提升和图谱索引。任一步失败都整体回滚。
- 物化知识复用现有 `documents/chunks` 授权检索路径，但以内部 `source_type=knowledge` 标记为托管内容；对外证据仍兼容 `source_type=document`，并增加 `origin_type=approved_knowledge`、候选 ID、PRD 版本 ID 与内容哈希。
- personal 知识按 tenant + owner 私有；team 知识按 tenant 向成员共享，owner 继续记录原 PRD 创建者。
- 批准后的知识版本不可通过普通文档删除接口移除。撤回、废弃或覆盖需要独立版本化业务决策，不能用 CRUD 删除绕过审计。
- 该链路沉淀的是经过人工确认的业务事实，不自动生成或合并 Skill 规则；坏案例到 Skill 规则仍属于工程维护平面。

## 结果

面试和验收可以证明“候选审批后被未来 RAG 命中”，同时保留原证据、审批者、PRD 版本和内容哈希。复用同一检索与授权实现避免出现第二套绕过 tenant/owner 过滤的知识查询路径；代价是托管知识必须通过专门治理流程演进，而不能按普通上传文档任意删除。
