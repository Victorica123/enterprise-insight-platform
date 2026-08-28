# 契约知识

机器可验证契约位于 `contracts/`。本文解释兼容策略与责任，不复制完整 schema。

## 共同信封

跨服务调用和事件至少携带：

- `tenant_id`：数据隔离主边界。
- `owner_id`：资源所有者；团队共享必须通过显式授权关系表达。
- `trace_id`：贯穿上传、转写、摄取、问答和审批。
- `event_id`：消息投递幂等键。
- `occurred_at`：带时区的业务发生时间。
- 资源 ID 与资源版本：防止旧事件覆盖新事实。

## 首个领域事件

`transcript.ready.v1` 表示某个媒体资产的一版转写已经成为可消费事实。它包含媒体元数据和有序片段，每个片段具有稳定 ID、`start_ms`、`end_ms`、可选说话人和文本。

机器契约为 `contracts/events/transcript-ready-v1.schema.json`，Agent 接收端点为 `POST /internal/v1/media/transcripts`，使用独立 Bearer 服务凭证，不接受用户 JWT 代替服务身份。

消费者按 `event_id` 去重，并按 `asset_id + transcript_version` 保证语义幂等。重复投递应返回成功；同一版本内容冲突应拒绝并告警。

## 证据引用

Agent 对外返回的通用证据结构区分 `document` 与 `video`。视频引用至少包含：

- `source_type=video`
- `asset_id`
- `segment_id`
- `start_ms`、`end_ms`
- 可选 `speaker`
- 引用文本与检索分数

引用中不包含永久公开 URL。前端使用资产身份向 Media Service 申请短期播放授权。

统一访问令牌声明由 `contracts/identity/jwt-claims-v1.schema.json` 定义。Agent 的生产模式校验 HS256 算法、签名、issuer、audience、时间窗口、`token_use=access`、tenant、subject、role 与 jti；开发兼容身份头不会在 production 模式启动。

## 版本策略

- 事件名称带版本后缀。
- 新增可选字段可留在当前版本；删除、改义、改变必填性需发布新版本。
- 生产者、消费者和 schema 都必须有契约测试。
- 未知可选字段应被消费者忽略；未知事件版本不得静默降级处理。
