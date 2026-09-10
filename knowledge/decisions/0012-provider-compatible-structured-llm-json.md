# ADR-0012：Agent 决策通道采用 provider-compatible 结构化 JSON

- 状态：已接受
- 日期：2026-09-01

## 背景

Router、检索 Planner 和 Tool Agent 的自由文本 JSON 容易出现缺字段、错误枚举、额外工具名或不可解析的参数。模型输出是不可信输入，不能直接决定检索范围或执行副作用。不同 OpenAI-compatible provider 对 Chat Completions 的 `response_format` 支持也不完全一致。

## 决策

- `app/llm_client.py` 统一允许调用方传入 `response_format`，并继续集中管理连接池、超时、重试和最大输出 token。
- `LLM_RESPONSE_FORMAT=auto` 时，OpenAI 请求 `json_schema` 且 `strict=true`；DeepSeek 兼容通道请求 `json_object`。`json_schema/json_object/off` 可显式选择，以便目标 gateway 做兼容性验证。
- 使用闭合的根对象 envelope：Planner 返回 `{ "queries": [...] }`，Tool Agent 返回 `{ "calls": [...] }`。Tool Agent 的不同工具参数编码为 `arguments_json` 字符串，解析后仍必须通过工具定义的参数、工具白名单、重复鉴权和审批策略。
- Router、Planner 和 Tool Agent 对响应执行 JSON 类型、字段/枚举、长度、参数对象和未知工具校验；provider 不支持、网络错误、拒答或解析失败记录降级并走确定性规则。不能把结构化响应当作事实正确性、引用正确性或安全授权证明。
- 六阶段 `analysis_pipeline.py` 保持确定性 specialist baseline。本 ADR 只改变问答侧的可选决策通道，不把项目包装成完整多 LLM Agent Runtime；后续若模型化 specialist，必须另做 evidence citation、Pydantic/JSON Schema、成本延迟和 holdout A/B 评测。

## 结果

结构化字段边界更明确，工具参数不会因为自由文本而直接进入执行层，且默认 DeepSeek 通道不会因不支持 strict schema 而每次失败。代价是 Tool Agent 参数需要 JSON 字符串编码、provider 行为仍需真实 smoke，结构化输出仍不能替代授权、证据校验、人工审批和业务评测。
