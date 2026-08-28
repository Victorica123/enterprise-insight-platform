"""V3 controlled tool layer: registry, validation, approval, and audit."""
from __future__ import annotations

import logging
import os
from dataclasses import dataclass
from time import perf_counter
from typing import Callable

from app.auth import OPERATOR_ROLES, WRITE_ROLES
from app.ticket_store import (
    PendingAction,
    claim_pending_action,
    complete_pending_action,
    create_pending_action,
    create_ticket,
    get_pending_action,
    get_ticket,
    list_tickets,
    record_tool_call,
    reject_pending_action,
    update_ticket_status,
    update_tool_call,
)


logger = logging.getLogger(__name__)

# 角色策略统一从 auth 模块取，避免双源漂移；别名保留给工具定义默认值。
READ_ROLES = OPERATOR_ROLES


@dataclass(frozen=True)
class ToolDefinition:
    name: str
    description: str
    parameters: dict
    handler: Callable[..., dict]
    operation: str = "read"
    requires_approval: bool = False
    allowed_roles: frozenset[str] = READ_ROLES
    approved_handler: Callable[..., dict] | None = None


@dataclass
class ToolCallResult:
    tool_name: str
    success: bool
    result: dict
    status: str
    duration_ms: float
    pending_action_id: str = ""


@dataclass
class ApprovalResolution:
    action_id: str
    status: str
    result: dict
    message: str
    already_resolved: bool = False


_TOOLS: dict[str, ToolDefinition] = {}


def register_tool(tool: ToolDefinition) -> None:
    if tool.name in _TOOLS:
        raise ValueError(f"Tool already registered: {tool.name}")
    _TOOLS[tool.name] = tool


def get_tool(name: str) -> ToolDefinition | None:
    return _TOOLS.get(name)


def list_tool_definitions() -> list[ToolDefinition]:
    return list(_TOOLS.values())


def get_tools_for_llm() -> list[dict]:
    return [
        {
            "name": tool.name,
            "description": tool.description,
            "parameters": tool.parameters,
            "requires_approval": tool.requires_approval,
        }
        for tool in _TOOLS.values()
    ]


def init_tools() -> None:
    if _TOOLS:
        return
    register_tool(
        ToolDefinition(
            name="query_tickets",
            description="查询工单列表，可按状态、优先级和关键词过滤。",
            parameters=_object_schema(
                {
                    "status": _string_schema(enum=["open", "in_progress", "resolved", "closed"]),
                    "priority": _string_schema(enum=["low", "medium", "high", "critical"]),
                    "keyword": _string_schema(max_length=100),
                }
            ),
            handler=_query_tickets,
        )
    )
    register_tool(
        ToolDefinition(
            name="get_ticket_detail",
            description="获取单个工单详情。",
            parameters=_object_schema({"ticket_id": _string_schema(max_length=64)}, ["ticket_id"]),
            handler=_get_ticket_detail,
        )
    )
    register_tool(
        ToolDefinition(
            name="create_ticket",
            description="生成新工单草稿；人工批准后才写入数据库。",
            parameters=_object_schema(
                {
                    "title": _string_schema(max_length=120),
                    "description": _string_schema(max_length=3000),
                    "priority": _string_schema(enum=["low", "medium", "high", "critical"]),
                    "assignee": _string_schema(max_length=80),
                    "risk_level": _string_schema(max_length=20),
                    "source_document_ids": {"type": "array", "items": {"type": "string"}, "maxItems": 20},
                },
                ["title", "description"],
            ),
            handler=_draft_create_ticket,
            operation="write",
            requires_approval=True,
            allowed_roles=WRITE_ROLES,
            approved_handler=_execute_create_ticket,
        )
    )
    register_tool(
        ToolDefinition(
            name="update_ticket_status",
            description="生成工单状态变更草稿；人工批准后才写入数据库。",
            parameters=_object_schema(
                {
                    "ticket_id": _string_schema(max_length=64),
                    "new_status": _string_schema(enum=["open", "in_progress", "resolved", "closed"]),
                    "assignee": _string_schema(max_length=80),
                },
                ["ticket_id", "new_status"],
            ),
            handler=_draft_update_status,
            operation="write",
            requires_approval=True,
            allowed_roles=WRITE_ROLES,
            approved_handler=_execute_update_status,
        )
    )


def execute_tool(
    name: str,
    arguments: dict,
    *,
    actor_role: str = "operator",
    actor_user: str = "anonymous",
    approval_ttl_seconds: int = 900,
) -> ToolCallResult:
    """Run one validated tool call or create an approval draft for writes."""
    init_tools()
    started_at = perf_counter()
    tool = get_tool(name)
    if tool is None:
        duration = _elapsed_ms(started_at)
        record_tool_call(
            tool_name=name,
            operation="unknown",
            requires_approval=False,
            status="failed",
            actor_role=actor_role,
            input_payload=_audit_payload(arguments),
            error_message="unknown_tool",
            duration_ms=duration,
        )
        return ToolCallResult(name, False, {"error": "未知工具。"}, "failed", duration)

    if actor_role not in tool.allowed_roles:
        duration = _elapsed_ms(started_at)
        record_tool_call(
            tool_name=name,
            operation=tool.operation,
            requires_approval=tool.requires_approval,
            status="denied",
            actor_role=actor_role,
            input_payload=_audit_payload(arguments),
            error_message="permission_denied",
            duration_ms=duration,
        )
        return ToolCallResult(name, False, {"error": "当前角色没有调用该工具的权限。"}, "denied", duration)

    try:
        validated = validate_arguments(tool, arguments)
    except ValueError as exc:
        duration = _elapsed_ms(started_at)
        record_tool_call(
            tool_name=name,
            operation=tool.operation,
            requires_approval=tool.requires_approval,
            status="failed",
            actor_role=actor_role,
            input_payload=_audit_payload(arguments),
            error_message=str(exc),
            duration_ms=duration,
        )
        return ToolCallResult(name, False, {"error": str(exc)}, "failed", duration)

    try:
        result = tool.handler(**validated)
        if "error" in result:
            raise ValueError(str(result["error"]))
        if not tool.requires_approval:
            duration = _elapsed_ms(started_at)
            record_tool_call(
                tool_name=name,
                operation=tool.operation,
                requires_approval=False,
                status="succeeded",
                actor_role=actor_role,
                input_payload=_audit_payload(validated),
                result=_audit_payload(result),
                duration_ms=duration,
            )
            return ToolCallResult(name, True, result, "succeeded", duration)

        call_id = record_tool_call(
            tool_name=name,
            operation=tool.operation,
            requires_approval=True,
            status="preparing",
            actor_role=actor_role,
            input_payload=_audit_payload(validated),
        )
        action, reused = create_pending_action(
            name,
            result["draft"],
            requested_by=actor_role,
            requested_by_user=actor_user,
            tool_call_id=call_id,
            ttl_seconds=approval_ttl_seconds,
        )
        duration = _elapsed_ms(started_at)
        status = "deduplicated" if reused else "pending"
        update_tool_call(
            call_id,
            status=status,
            action_id=action.action_id,
            result={"pending_action_id": action.action_id, "reused": reused},
            duration_ms=duration,
        )
        return ToolCallResult(name, True, result, status, duration, action.action_id)
    except Exception as exc:
        duration = _elapsed_ms(started_at)
        record_tool_call(
            tool_name=name,
            operation=tool.operation,
            requires_approval=tool.requires_approval,
            status="failed",
            actor_role=actor_role,
            input_payload=_audit_payload(arguments),
            error_message=str(exc),
            duration_ms=duration,
        )
        return ToolCallResult(name, False, {"error": str(exc)}, "failed", duration)


def _approval_sod_enforced() -> bool:
    """职责分离开关：默认开启；演示单人流可设 APPROVAL_SOD_ENFORCED=0。"""
    return os.getenv("APPROVAL_SOD_ENFORCED", "1").strip().lower() not in {"0", "false", "no", "off"}


def resolve_tool_action(
    action_id: str,
    approved: bool,
    *,
    actor_role: str,
    actor_user: str = "anonymous",
) -> ApprovalResolution:
    """Resolve an approval with atomic claiming and duplicate-request idempotency."""
    started_at = perf_counter()
    init_tools()
    action = get_pending_action(action_id)
    if action is None:
        return ApprovalResolution(action_id, "not_found", {}, "待审批操作不存在。")
    tool = get_tool(action.action_type)
    if tool is None:
        return ApprovalResolution(action_id, "failed", {}, "审批关联的工具不存在。")
    if actor_role not in tool.allowed_roles:
        record_tool_call(
            tool_name=tool.name,
            operation="approval",
            requires_approval=True,
            status="denied",
            actor_role=actor_role,
            input_payload={"action_id": action_id, "approved": approved},
            error_message="permission_denied",
        )
        return ApprovalResolution(action_id, "denied", {}, "当前角色没有审批权限。")
    if action.status not in {"pending", "executing"}:
        return _resolved_response(action, already_resolved=True)

    # 职责分离：发起人不能审批自己的写操作（双方身份都明确时才比对，
    # 匿名请求保持原演示体验；生产环境接入真实认证后身份始终明确）。
    if (
        approved
        and _approval_sod_enforced()
        and actor_user != "anonymous"
        and action.requested_by_user == actor_user
    ):
        logger.warning(
            "separation_of_duties_denied action_id=%s user=%s", action_id, actor_user
        )
        record_tool_call(
            tool_name=tool.name,
            operation="approval",
            requires_approval=True,
            status="denied",
            actor_role=actor_role,
            input_payload={"action_id": action_id, "approved": approved},
            error_message="separation_of_duties",
        )
        return ApprovalResolution(
            action_id, "denied", {}, "职责分离：发起人不能审批自己发起的写操作，请由其他人审批。"
        )

    if not approved:
        resolved = reject_pending_action(action_id, actor_role)
        if resolved is None:
            return ApprovalResolution(action_id, "not_found", {}, "待审批操作不存在。")
        update_tool_call(
            resolved.tool_call_id,
            status=resolved.status,
            action_id=action_id,
            result={"decision": resolved.status},
            duration_ms=_elapsed_ms(started_at),
        )
        return _resolved_response(resolved)

    claimed, acquired = claim_pending_action(action_id, actor_role)
    if claimed is None:
        return ApprovalResolution(action_id, "not_found", {}, "待审批操作不存在。")
    if not acquired and claimed.status == "executing":
        return ApprovalResolution(action_id, "executing", {}, "该操作正在由另一个请求执行，请稍后刷新。")
    if claimed.status != "executing":
        if claimed.status == "expired":
            update_tool_call(
                claimed.tool_call_id,
                status="expired",
                action_id=action_id,
                duration_ms=_elapsed_ms(started_at),
            )
        return _resolved_response(claimed, already_resolved=claimed.status in {"succeeded", "failed"})

    try:
        validated = validate_arguments(tool, claimed.payload)
        if tool.approved_handler is None:
            raise RuntimeError("工具没有配置审批执行器。")
        result = tool.approved_handler(**validated)
        if "error" in result:
            raise RuntimeError(str(result["error"]))
        duration = _elapsed_ms(started_at)
        completed = complete_pending_action(
            action_id,
            succeeded=True,
            result=result,
            error_message="",
            duration_ms=duration,
        )
        update_tool_call(
            claimed.tool_call_id,
            status="succeeded",
            action_id=action_id,
            result=_audit_payload(result),
            duration_ms=duration,
        )
        return _resolved_response(completed or claimed)
    except Exception as exc:
        duration = _elapsed_ms(started_at)
        completed = complete_pending_action(
            action_id,
            succeeded=False,
            result={},
            error_message=str(exc),
            duration_ms=duration,
        )
        update_tool_call(
            claimed.tool_call_id,
            status="failed",
            action_id=action_id,
            error_message=str(exc),
            duration_ms=duration,
        )
        return _resolved_response(completed or claimed)


def validate_arguments(tool: ToolDefinition, arguments: dict) -> dict:
    if not isinstance(arguments, dict):
        raise ValueError("工具参数必须是对象。")
    properties = tool.parameters.get("properties", {})
    required = set(tool.parameters.get("required", []))
    unknown = set(arguments) - set(properties)
    if unknown:
        raise ValueError(f"包含未声明参数：{', '.join(sorted(unknown))}")
    missing = [name for name in required if name not in arguments or arguments[name] in {None, ""}]
    if missing:
        raise ValueError(f"缺少必填参数：{', '.join(sorted(missing))}")

    validated: dict = {}
    for name, value in arguments.items():
        spec = properties[name]
        expected = spec.get("type")
        if expected == "string":
            if not isinstance(value, str):
                raise ValueError(f"参数 {name} 必须是字符串。")
            value = value.strip()
            if len(value) > int(spec.get("maxLength", 10_000)):
                raise ValueError(f"参数 {name} 超过长度限制。")
            if spec.get("enum") and value not in spec["enum"]:
                raise ValueError(f"参数 {name} 不在允许范围内。")
        elif expected == "array":
            if not isinstance(value, list) or not all(isinstance(item, str) for item in value):
                raise ValueError(f"参数 {name} 必须是字符串数组。")
            if len(value) > int(spec.get("maxItems", 100)):
                raise ValueError(f"参数 {name} 数量超过限制。")
        validated[name] = value
    return validated


def _query_tickets(status: str = "", priority: str = "", keyword: str = "") -> dict:
    tickets = list_tickets(status=status or None, priority=priority or None, keyword=keyword, limit=20)
    return {"count": len(tickets), "tickets": [ticket.to_dict() for ticket in tickets]}


def _get_ticket_detail(ticket_id: str) -> dict:
    ticket = get_ticket(ticket_id)
    return ticket.to_dict() if ticket else {"error": f"工单 {ticket_id} 不存在。"}


def _draft_create_ticket(**payload) -> dict:
    return {
        "action": "create_ticket",
        "status": "pending_approval",
        "draft": payload,
        "message": "工单草稿已生成，需要人工确认后才会创建。",
    }


def _execute_create_ticket(**payload) -> dict:
    ticket = create_ticket(status="open", **payload)
    return {"action": "created", "ticket": ticket.to_dict(), "message": "工单已创建。"}


def _draft_update_status(ticket_id: str, new_status: str, assignee: str = "") -> dict:
    ticket = get_ticket(ticket_id)
    if ticket is None:
        return {"error": f"工单 {ticket_id} 不存在。"}
    return {
        "action": "update_ticket_status",
        "status": "pending_approval",
        "draft": {"ticket_id": ticket_id, "new_status": new_status, "assignee": assignee},
        "display": {"title": ticket.title, "current_status": ticket.status},
        "message": f"状态变更草稿已生成：{ticket.status} -> {new_status}。",
    }


def _execute_update_status(ticket_id: str, new_status: str, assignee: str = "") -> dict:
    ticket = update_ticket_status(ticket_id, new_status, assignee=assignee or None)
    if ticket is None:
        return {"error": f"工单 {ticket_id} 不存在。"}
    return {"action": "updated", "ticket": ticket.to_dict(), "message": "工单状态已更新。"}


def _resolved_response(action: PendingAction, already_resolved: bool = False) -> ApprovalResolution:
    messages = {
        "succeeded": "操作已批准并执行。",
        "failed": f"操作执行失败：{action.error_message}",
        "rejected": "操作已被拒绝，未产生业务写入。",
        "expired": "审批已过期，未产生业务写入。",
        "executing": "操作正在执行，请稍后刷新。",
        "pending": "操作仍在等待审批。",
    }
    return ApprovalResolution(
        action_id=action.action_id,
        status=action.status,
        result=action.result,
        message=messages.get(action.status, action.status),
        already_resolved=already_resolved,
    )


def _object_schema(properties: dict, required: list[str] | None = None) -> dict:
    schema = {"type": "object", "properties": properties, "additionalProperties": False}
    if required:
        schema["required"] = required
    return schema


def _string_schema(*, enum: list[str] | None = None, max_length: int = 200) -> dict:
    schema: dict[str, object] = {"type": "string", "maxLength": max_length}
    if enum:
        schema["enum"] = enum
    return schema


def _audit_payload(value, depth: int = 0):
    """Bound audit size; production systems should additionally redact domain secrets."""
    if depth > 3:
        return "[truncated]"
    if isinstance(value, dict):
        return {str(key)[:80]: _audit_payload(item, depth + 1) for key, item in list(value.items())[:30]}
    if isinstance(value, list):
        return [_audit_payload(item, depth + 1) for item in value[:20]]
    if isinstance(value, str):
        return value[:500]
    return value


def _elapsed_ms(started_at: float) -> float:
    return round((perf_counter() - started_at) * 1000, 2)
