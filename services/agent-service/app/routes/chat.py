"""聊天端点：编排 standard/agentic RAG，并记录指标与请求日志。"""

import logging
from time import perf_counter

from fastapi import APIRouter, Depends, HTTPException

from app.agentic_rag import answer_agentic_question  # compatibility patch target
from app.architecture.context import RequestContext
from app.architecture.observability import record_chat_log, record_chat_metric
from app.architecture.orchestration import answer_chat
from app.auth import ActorPrincipal, current_principal
from app.model_egress import (
    bind_model_egress_tenant,
    is_model_egress_allowed,
    reset_model_egress_tenant,
)
from app.models import ChatRequest, ChatResponse
from app.rag import answer_question  # compatibility patch target

logger = logging.getLogger(__name__)

router = APIRouter(tags=["chat"])


@router.post(
    "/chat",
    response_model=ChatResponse,
    summary="知识库问答（standard / agentic）",
    responses={
        200: {"description": "回答 + 来源证据 + 执行轨迹 + token 用量 + 待审批操作"}
    },
)
def chat(
    request: ChatRequest,
    principal: ActorPrincipal = Depends(current_principal),
) -> ChatResponse:
    if not request.question.strip():
        raise HTTPException(status_code=400, detail="Question cannot be empty.")
    if request.answer_mode == "api" and not is_model_egress_allowed(principal.tenant_id):
        raise HTTPException(
            status_code=403,
            detail="该工作区尚未获批向外部模型发送数据，请使用本地回答模式或联系管理员。",
        )

    context = RequestContext.from_principal(principal)
    actor_role = context.role
    actor_user = context.actor_user
    retrieval_scope = (
        context.retrieval_scope(request.asset_ids)
        if principal.auth_mode == "jwt" or request.asset_ids
        else None
    )
    started_at = perf_counter()
    egress_token = bind_model_egress_tenant(principal.tenant_id)
    try:
        response = answer_chat(
            request.question,
            workflow_mode=request.workflow_mode,
            answer_mode=request.answer_mode,
            retriever_mode=request.retriever_mode,
            actor_role=actor_role,
            actor_user=actor_user,
            workspace_type=principal.workspace_type,
            retrieval_scope=retrieval_scope,
            agentic_handler=answer_agentic_question,
            standard_handler=answer_question,
        )
    except Exception:
        logger.exception(
            "chat_failed workflow=%s mode=%s",
            request.workflow_mode,
            request.answer_mode,
        )
        safe_record_chat_metric(
            request=request,
            response=None,
            latency_ms=(perf_counter() - started_at) * 1000,
            outcome="error",
            principal=principal,
        )
        raise
    finally:
        reset_model_egress_tenant(egress_token)

    summary = response.agent_summary
    outcome = (
        "answered"
        if summary and summary.evidence_status in {"passed", "not_required"}
        else infer_standard_outcome(response)
    )
    log_id = safe_record_chat_metric(
        request=request,
        response=response,
        latency_ms=(perf_counter() - started_at) * 1000,
        outcome=outcome,
        principal=principal,
    )
    if isinstance(log_id, int):
        response.log_id = log_id
    return response


def infer_standard_outcome(response: ChatResponse) -> str:
    if response.agent_summary:
        return "refused"
    refused_markers = [
        "不能可靠回答",
        "证据强度不足",
        "没有足够相关",
        "还没有可用资料",
        "没有在已上传资料中找到",
    ]
    return (
        "refused"
        if any(marker in response.answer for marker in refused_markers)
        else "answered"
    )


def safe_record_chat_metric(
    *,
    request: ChatRequest,
    response: ChatResponse | None,
    latency_ms: float,
    outcome: str,
    principal: ActorPrincipal | None = None,
) -> int:
    """记录指标 + 请求日志（含 token 成本），返回日志 ID 供反馈使用。"""
    try:
        tenant_id = (
            principal.tenant_id
            if principal and principal.auth_mode == "jwt"
            else "legacy"
        )
        owner_id = (
            principal.user_id
            if principal and principal.auth_mode == "jwt"
            else "legacy"
        )
        summary = response.agent_summary if response else None
        usage = response.token_usage if response else None
        answer_status = "error"
        if response:
            answer_step = next(
                (step for step in reversed(response.trace) if step.name == "answer"),
                None,
            )
            answer_status = answer_step.status if answer_step else "not_generated"

        record_chat_metric(
            workflow_mode=request.workflow_mode,
            answer_mode=request.answer_mode,
            retriever_mode=request.retriever_mode,
            intent=summary.intent if summary else "standard",
            complexity=summary.complexity if summary else "standard",
            retrieval_rounds=summary.retrieval_rounds if summary else 1,
            query_count=len(summary.queries) if summary else 1,
            evidence_status=summary.evidence_status
            if summary
            else ("passed" if outcome == "answered" else "refused"),
            citation_status=summary.citation_status if summary else "not_applicable",
            source_count=len(response.sources) if response else 0,
            outcome=outcome,
            answer_status=answer_status,
            latency_ms=round(latency_ms, 2),
            answer_chars=len(response.answer) if response else 0,
            prompt_tokens=usage.prompt_tokens if usage else 0,
            completion_tokens=usage.completion_tokens if usage else 0,
            total_tokens=usage.total_tokens if usage else 0,
            estimated_cost_usd=usage.estimated_cost_usd if usage else 0.0,
            tenant_id=tenant_id,
            owner_id=owner_id,
        )
        return record_chat_log(
            question=request.question,
            workflow_mode=request.workflow_mode,
            answer_mode=request.answer_mode,
            retriever_mode=request.retriever_mode,
            intent=summary.intent if summary else "standard",
            outcome=outcome,
            evidence_status=summary.evidence_status if summary else "",
            citation_status=summary.citation_status if summary else "",
            source_count=len(response.sources) if response else 0,
            latency_ms=round(latency_ms, 2),
            total_tokens=usage.total_tokens if usage else 0,
            estimated_cost_usd=usage.estimated_cost_usd if usage else 0.0,
            answer_preview=response.answer[:400] if response else "",
            trace=[step.model_dump() for step in response.trace] if response else [],
            sources=[
                {
                    **source.model_dump(mode="json"),
                    "content": source.content[:1000],
                }
                for source in response.sources
            ]
            if response
            else [],
            tenant_id=tenant_id,
            owner_id=owner_id,
        )
    except Exception:
        logger.exception("Failed to record chat metric")
        return 0
