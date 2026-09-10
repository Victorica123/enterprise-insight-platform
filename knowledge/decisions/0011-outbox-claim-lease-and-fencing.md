# ADR-0011：Media Outbox 使用条件 Claim/Lease 保护多实例投递

- 状态：已接受
- 日期：2026-09-01

## 背景

`transcript.ready.v1` 必须与 Media 任务完成在同一事务写入 outbox。仅由 dispatcher 读取 `PENDING`、执行网络发送再更新结果，在单实例可以工作，但多实例会重复领取同一事件，并可能竞争 attempts 或覆盖较新的结果。网络发送也可能在进程崩溃、超时或 lease 过期后继续返回。

## 决策

- `integration_event_outbox` 使用 `PENDING → CLAIMED → SENT/DEAD` 状态；暂时性失败从 `CLAIMED` 回到带 `nextAttemptAt` 的 `PENDING`。
- 领取先读取有界候选，再用 `eventId + status + nextAttemptAt/claimExpiresAt` 条件 UPDATE 设置随机 `claimId` 和 `claimExpiresAt`。候选读取不是所有权证明，只有更新行数为 1 才算领取成功。
- 成功和失败落库都校验 `eventId + CLAIMED + claimId + lease 未过期`；失败还校验 expected attempts。过期 claim 可以被后续 worker 接管，旧 worker 的迟到结果只能得到 false，不能覆盖新 worker。
- 重试采用有界指数退避；永久契约错误或超过 `maxAttempts` 进入 `DEAD`，错误文本截断保存。下游 Agent 仍按 `event_id` 和资产/版本语义双重幂等，因此整体语义是 at-least-once，不是 exactly-once。
- 当前实现保留 JPA/H2 兼容路径；正式 MySQL/PostgreSQL 迁移时必须用版本化 schema、索引和目标数据库锁行为验证，必要时采用 `SKIP LOCKED` 或等价原子领取，并为 oldest age、attempts、lease loss 和 DEAD 配置告警。

## 结果

同一事件的多实例 dispatcher 不会因为普通候选竞争而同时拥有有效 lease，旧 worker 不能提交迟到结果，失败可恢复且重试耗尽可见。代价是增加 claim 字段、条件更新和运维指标；真实数据库、网络故障注入、进程重启和跨实例吞吐仍需目标环境验证。
