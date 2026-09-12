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
from typing import Any

from app.call_limits import CallLimitExceeded
from app.config import get_llm_settings
from app.llm import is_llm_configured
from app.llm_client import create_chat_completion
from app.prompts import load_prompt, render_prompt
from app.tools import get_tools_for_llm

logger = logging.getLogger(__name__)

INTENT_OPTIONS = ["risk", "causal", "fact", "summary", "general"]

_ROUTER_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "intent": {"type": "string", "enum": INTENT_OPTIONS},
        "complexity": {"type": "string", "enum": ["simple", "complex"]},
    },
    "required": ["intent", "complexity"],
    "additionalProperties": False,
}
_QUERY_PLAN_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "queries": {
            "type": "array",
            "items": {"type": "string", "minLength": 1, "maxLength": 25},
            "minItems": 1,
            "maxItems": 6,
        }
    },
    "required": ["queries"],
    "additionalProperties": False,
}
_TOOL_CALL_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "calls": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "tool": {"type": "string", "minLength": 1, "maxLength": 80},
                    # A JSON string keeps the strict schema closed while allowing
                    # each registered tool to have a different argument object.
                    "arguments_json": {"type": "string", "maxLength": 4000},
                },
                "required": ["tool", "arguments_json"],
                "additionalProperties": False,
            },
            "maxItems": 4,
        }
    },
    "required": ["calls"],
    "additionalProperties": False,
}


def _llm_router_enabled() -> bool:
    """LLM 路由开关：离线门禁与测试设 LLM_ROUTER_ENABLED=0，保证确定性且不消耗 API 额度。"""
    return os.getenv("LLM_ROUTER_ENABLED", "1").strip().lower() not in {
        "0",
        "false",
        "no",
        "off",
    }


@dataclass(frozen=True)
class LLMJsonResult[JsonResult]:
    data: JsonResult
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


def _response_format(schema_name: str, schema: dict[str, Any]) -> dict[str, Any] | None:
    """Select a provider-compatible structured response mode.

    OpenAI supports strict JSON Schema.  DeepSeek's OpenAI-compatible endpoint
    currently supports JSON Object mode, so keep the same closed top-level
    envelopes while letting the existing parser validate semantic fields.
    ``LLM_RESPONSE_FORMAT=off`` is an explicit escape hatch for compatible
    gateways that reject the ``response_format`` parameter.
    """
    mode = os.getenv("LLM_RESPONSE_FORMAT", "auto").strip().lower()
    if mode in {"off", "none", "disabled"}:
        return None
    if mode == "json_object" or (
        mode == "auto" and get_llm_settings().provider != "openai"
    ):
        return {"type": "json_object"}
    return {
        "type": "json_schema",
        "json_schema": {
            "name": schema_name,
            "strict": True,
            "schema": schema,
        },
    }


def _chat_json(
    system: str,
    user: str,
    *,
    schema_name: str,
    schema: dict[str, Any],
) -> LLMJsonResult[dict[str, Any] | list[Any]] | None:
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
            response_format=_response_format(schema_name, schema),
            purpose=schema_name,
        )
    except CallLimitExceeded as exc:  # 阶段 0.4：预算耗尽走规则，不是故障
        logger.warning(
            "llm_router_call_limit purpose=%s limit=%s fallback=rules", schema_name, exc.limit
        )
        return None
    except Exception as exc:  # provider failures must preserve rules fallback
        logger.warning("llm_router_request_failed error=%s fallback=rules", exc)
        return None

    try:
        content = response.choices[0].message.content or ""
        usage = getattr(response, "usage", None)
        parsed = json.loads(_extract_json(content))
    except (AttributeError, IndexError, TypeError, ValueError) as exc:
        logger.warning(
            "llm_router_json_parse_failed error=%s content_prefix=%.80r fallback=rules",
            exc,
            locals().get("content", ""),
        )
        return None
    if not isinstance(parsed, (dict, list)):
        logger.warning(
            "llm_router_unexpected_json_type=%s fallback=rules", type(parsed).__name__
        )
        return None
    return LLMJsonResult(
        data=parsed,
        prompt_tokens=_usage_token_count(usage, "prompt_tokens"),
        completion_tokens=_usage_token_count(usage, "completion_tokens"),
    )


def _usage_token_count(usage: object, field: str) -> int:
    try:
        return max(0, int(getattr(usage, field, 0) or 0))
    except (TypeError, ValueError):
        return 0


def _extract_json(text: str) -> str:
    text = text.strip()
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?\s*", "", text)
        text = re.sub(r"\s*```$", "", text)
    return text


def llm_route_question(question: str) -> RouterDecision | None:
    """LLM 路由：意图 + 复杂度；失败返回 None。"""
    result = _chat_json(
        load_prompt("router_system"),
        render_prompt("router_user", question=question),
        schema_name="router_decision_v1",
        schema=_ROUTER_SCHEMA,
    )
    if result is None or not isinstance(result.data, dict):
        return None
    intent = str(result.data.get("intent", "general")).strip().lower()
    if intent not in INTENT_OPTIONS:
        intent = "general"
    complexity = (
        "complex"
        if str(result.data.get("complexity", "simple")).strip().lower() == "complex"
        else "simple"
    )
    return RouterDecision(
        intent=intent,
        complexity=complexity,
        prompt_tokens=result.prompt_tokens,
        completion_tokens=result.completion_tokens,
    )


def llm_plan_queries(question: str, intent: str) -> LLMJsonResult[list[str]] | None:
    """LLM 检索规划：改写/扩展查询（含同义表述与关键实体）；失败返回 None。"""
    result = _chat_json(
        load_prompt("planner_system"),
        render_prompt("planner_user", question=question, intent=intent),
        schema_name="query_plan_v1",
        schema=_QUERY_PLAN_SCHEMA,
    )
    if result is None:
        return None
    raw_queries = (
        result.data.get("queries") if isinstance(result.data, dict) else result.data
    )
    if not isinstance(raw_queries, list):
        return None
    queries = [str(q).strip() for q in raw_queries if str(q).strip()]
    if not queries:
        return None
    return LLMJsonResult(
        data=queries[:6],
        prompt_tokens=result.prompt_tokens,
        completion_tokens=result.completion_tokens,
    )


def llm_select_tool_calls(
    question: str,
) -> LLMJsonResult[list[tuple[str, dict[str, Any]]]] | None:
    """LLM 工具选择（B2）：返回 (工具名, 参数) 列表；失败返回 None 走关键词规则。"""
    tools = get_tools_for_llm()
    result = _chat_json(
        render_prompt("tool_selector_system", tools_json=json.dumps(tools, ensure_ascii=False)),
        render_prompt("tool_selector_user", question=question),
        schema_name="tool_calls_v1",
        schema=_TOOL_CALL_SCHEMA,
    )
    if result is None:
        return None
    raw_calls = (
        result.data.get("calls") if isinstance(result.data, dict) else result.data
    )
    if not isinstance(raw_calls, list):
        return None
    calls: list[tuple[str, dict]] = []
    for item in raw_calls[:4]:
        if not isinstance(item, dict):
            continue
        tool = str(item.get("tool", "")).strip()
        arguments = item.get("arguments")
        if not isinstance(arguments, dict):
            encoded_arguments = item.get("arguments_json")
            if isinstance(encoded_arguments, str):
                try:
                    arguments = json.loads(encoded_arguments)
                except json.JSONDecodeError:
                    arguments = None
        if tool and isinstance(arguments, dict):
            calls.append((tool, arguments))
    return LLMJsonResult(
        data=calls,
        prompt_tokens=result.prompt_tokens,
        completion_tokens=result.completion_tokens,
    )
