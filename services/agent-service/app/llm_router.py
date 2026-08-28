"""B1/B2：Router / Planner / 工具选择的 LLM 化通道（规则版为降级路径）。

契约约定（与规则版一致）：
- 输入问题文本，返回结构化结果；
- 未配置 Key、网络失败、输出解析失败一律返回 None，调用方回退规则版；
- 每次调用都带回真实 token 用量，供 V5 成本核算合并。
"""
from __future__ import annotations

import json
import logging
import os
import re
from dataclasses import dataclass

from app.llm_client import create_chat_completion
from app.llm import is_llm_configured
from app.tools import get_tools_for_llm


logger = logging.getLogger(__name__)

INTENT_OPTIONS = ["risk", "causal", "fact", "summary", "general"]


def _llm_router_enabled() -> bool:
    """LLM 路由开关：离线门禁与测试设 LLM_ROUTER_ENABLED=0，保证确定性且不消耗 API 额度。"""
    return os.getenv("LLM_ROUTER_ENABLED", "1").strip().lower() not in {"0", "false", "no", "off"}


@dataclass(frozen=True)
class LLMJsonResult:
    data: object
    prompt_tokens: int = 0
    completion_tokens: int = 0

    @property
    def total_tokens(self) -> int:
        return self.prompt_tokens + self.completion_tokens


@dataclass(frozen=True)
class RouterDecision:
    intent: str
    complexity: str
    source: str = "llm"
    prompt_tokens: int = 0
    completion_tokens: int = 0

    @property
    def total_tokens(self) -> int:
        return self.prompt_tokens + self.completion_tokens


def _chat_json(system: str, user: str) -> LLMJsonResult | None:
    """调用 LLM 并解析 JSON；任何失败返回 None（调用方回退规则版）。

    降级必须留痕：服务端记 warning 日志，否则路由静默回退无从排查。
    """
    if not _llm_router_enabled():
        return None
    if not is_llm_configured():
        return None
    try:
        response = create_chat_completion(
            messages=[
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            temperature=0.1,
        )
    except Exception as exc:  # pragma: no cover - 网络/限流等
        logger.warning("llm_router_request_failed error=%s fallback=rules", exc)
        return None

    content = response.choices[0].message.content or ""
    usage = getattr(response, "usage", None)
    try:
        parsed = json.loads(_extract_json(content))
    except (json.JSONDecodeError, ValueError):
        logger.warning(
            "llm_router_json_parse_failed content_prefix=%.80r fallback=rules", content
        )
        return None
    if not isinstance(parsed, (dict, list)):
        logger.warning("llm_router_unexpected_json_type=%s fallback=rules", type(parsed).__name__)
        return None
    return LLMJsonResult(
        data=parsed,
        prompt_tokens=int(getattr(usage, "prompt_tokens", 0) or 0),
        completion_tokens=int(getattr(usage, "completion_tokens", 0) or 0),
    )


def _extract_json(text: str) -> str:
    text = text.strip()
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?\s*", "", text)
        text = re.sub(r"\s*```$", "", text)
    return text


def llm_route_question(question: str) -> RouterDecision | None:
    """LLM 路由：意图 + 复杂度；失败返回 None。"""
    system = (
        "你是企业知识库工作流的路由器。分析用户问题，只输出 JSON："
        '{"intent": "risk|causal|fact|summary|general", "complexity": "simple|complex"}。'
        "intent 判定：涉及风险/违约/赔偿 -> risk；询问原因/延期/导致 -> causal；"
        "询问具体事实（负责人/日期/数量/编号/时限）-> fact；要求总结概括 -> summary；其他 -> general。"
        "complexity：多主题、多问句、超过 40 字或含“以及/同时/并且/是否/要不要” -> complex，否则 simple。"
        "不要输出 JSON 以外的内容。"
    )
    result = _chat_json(system, f"用户问题：{question}")
    if result is None or not isinstance(result.data, dict):
        return None
    intent = str(result.data.get("intent", "general")).strip().lower()
    if intent not in INTENT_OPTIONS:
        intent = "general"
    complexity = "complex" if str(result.data.get("complexity", "simple")).strip().lower() == "complex" else "simple"
    return RouterDecision(
        intent=intent,
        complexity=complexity,
        prompt_tokens=result.prompt_tokens,
        completion_tokens=result.completion_tokens,
    )


def llm_plan_queries(question: str, intent: str) -> LLMJsonResult | None:
    """LLM 检索规划：改写/扩展查询（含同义表述与关键实体）；失败返回 None。"""
    system = (
        "你是检索规划器。把用户问题改写成适合企业知识库检索的查询列表，只输出 JSON 字符串数组。"
        "要求：保留原问题作为第一个元素；补写 2-4 个查询，覆盖同义表述、关键实体与专业术语；"
        "每个查询 4-25 字。不要输出 JSON 以外的内容。"
    )
    result = _chat_json(system, f"用户问题：{question}\n路由意图：{intent}")
    if result is None or not isinstance(result.data, list):
        return None
    queries = [str(q).strip() for q in result.data if str(q).strip()]
    if not queries:
        return None
    return LLMJsonResult(
        data=queries[:6],
        prompt_tokens=result.prompt_tokens,
        completion_tokens=result.completion_tokens,
    )


def llm_select_tool_calls(question: str) -> LLMJsonResult | None:
    """LLM 工具选择（B2）：返回 (工具名, 参数) 列表；失败返回 None 走关键词规则。"""
    tools = get_tools_for_llm()
    system = (
        "你是工具调用决策器。根据用户问题决定调用哪些工具（可能 0 个），只输出 JSON 数组："
        '[{"tool": "工具名", "arguments": {...}}, ...]。'
        "查询类工具直接调用；创建/更新工单类写操作也返回（系统会进入人工审批流程）。"
        "与工单完全无关的问题返回 []。arguments 严格使用工具声明里的参数名。"
        f"可用工具：{json.dumps(tools, ensure_ascii=False)}。不要输出 JSON 以外的内容。"
    )
    result = _chat_json(system, f"用户问题：{question}")
    if result is None or not isinstance(result.data, list):
        return None
    calls: list[tuple[str, dict]] = []
    for item in result.data[:4]:
        if not isinstance(item, dict):
            continue
        tool = str(item.get("tool", "")).strip()
        arguments = item.get("arguments")
        if tool and isinstance(arguments, dict):
            calls.append((tool, arguments))
    return LLMJsonResult(
        data=calls,
        prompt_tokens=result.prompt_tokens,
        completion_tokens=result.completion_tokens,
    )
