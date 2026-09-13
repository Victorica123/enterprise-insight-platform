"""观测端点：指标、请求日志、工具调用审计。

隐私分层：/metrics/* 是聚合数据对所有角色开放；
/chat-logs、/tool-calls 含问题原文与工具入参，仅 operator/admin 可见。
"""
from fastapi import APIRouter, Depends, HTTPException

from app.architecture.observability import (
    get_chat_log,
    get_chat_metrics_summary,
    get_tool_metrics_summary,
    list_chat_logs,
    list_tool_call_logs,
    set_chat_log_feedback,
)
from app.auth import ActorPrincipal, current_principal, require_operator_role
from app.models import (
    ChatLogDetailResponse,
    ChatLogResponse,
    ChatMetricsSummary,
    FeedbackRequest,
    FeedbackResponse,
    ToolCallLogResponse,
    ToolMetricsSummary,
)

router = APIRouter(tags=["observability"])


def _tenant_scope(principal: ActorPrincipal) -> str | None:
    return principal.tenant_id if principal.auth_mode == "jwt" else None


def _owner_scope(principal: ActorPrincipal) -> str | None:
    return principal.resource_owner_id if principal.auth_mode == "jwt" else None


@router.get("/metrics/summary", response_model=ChatMetricsSummary, summary="问答指标汇总（请求量/回答率/P95/token/成本/满意度）")
def get_metrics_summary(principal: ActorPrincipal = Depends(current_principal)) -> ChatMetricsSummary:
    return ChatMetricsSummary(**get_chat_metrics_summary(tenant_id=_tenant_scope(principal)))


@router.get("/metrics/tools", response_model=ToolMetricsSummary, summary="工具调用指标（成功率/审批率/耗时/重复执行违规）")
def get_tool_metrics(principal: ActorPrincipal = Depends(current_principal)) -> ToolMetricsSummary:
    return ToolMetricsSummary(**get_tool_metrics_summary(tenant_id=_tenant_scope(principal)))


@router.get("/tool-calls", response_model=list[ToolCallLogResponse], summary="工具调用审计日志（operator+）")
def get_tool_calls(
    limit: int = 50,
    principal: ActorPrincipal = Depends(current_principal),
) -> list[ToolCallLogResponse]:
    require_operator_role(principal.role)
    return [
        ToolCallLogResponse(**item)
        for item in list_tool_call_logs(limit=limit, tenant_id=_tenant_scope(principal))
    ]


@router.get("/chat-logs", response_model=list[ChatLogResponse], summary="请求日志（可按 outcome 过滤，operator+）")
def get_chat_logs(
    outcome: str = "",
    limit: int = 50,
    principal: ActorPrincipal = Depends(current_principal),
) -> list[ChatLogResponse]:
    require_operator_role(principal.role)
    return [
        ChatLogResponse(**item)
        for item in list_chat_logs(
            outcome=outcome, limit=limit, tenant_id=_tenant_scope(principal),
        )
    ]


@router.get("/chat-logs/{log_id}", response_model=ChatLogDetailResponse, summary="单条日志详情 + trace 回放（operator+）")
def get_chat_log_detail(
    log_id: int,
    principal: ActorPrincipal = Depends(current_principal),
) -> ChatLogDetailResponse:
    require_operator_role(principal.role)
    log = get_chat_log(log_id, tenant_id=_tenant_scope(principal))
    if log is None:
        raise HTTPException(status_code=404, detail="Chat log not found.")
    return ChatLogDetailResponse(**log)


@router.post("/chat-logs/{log_id}/feedback", response_model=FeedbackResponse, summary="回答反馈（up/down + 备注）")
def submit_chat_feedback(
    log_id: int,
    request: FeedbackRequest,
    principal: ActorPrincipal = Depends(current_principal),
) -> FeedbackResponse:
    feedback = 1 if request.rating == "up" else -1
    if not set_chat_log_feedback(
        log_id,
        feedback,
        request.note,
        tenant_id=_tenant_scope(principal),
        owner_id=_owner_scope(principal),
    ):
        raise HTTPException(status_code=404, detail="Chat log not found.")
    return FeedbackResponse(log_id=log_id, feedback=feedback, feedback_note=request.note)
