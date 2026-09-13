"""Chat outcome, metrics and audit projection, independent of HTTP transport."""

import logging

from app.architecture.observability import record_chat_log, record_chat_metric
from app.architecture.planning import ExecutionPlan
from app.auth import ActorPrincipal
from app.models import ChatRequest, ChatResponse

logger = logging.getLogger(__name__)


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
    plan: ExecutionPlan | None = None,
) -> int:
    """记录指标 + 请求日志（含 token 成本、影子路由），返回日志 ID 供反馈使用。"""
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
            # 阶段 0.8 影子路由：用户选了什么（workflow_mode）/ 服务端执行了什么 / 系统自己会选什么
            execution_mode=plan.mode if plan else "",
            shadow_mode=plan.shadow_mode if plan else "",
            mode_agreement=plan.mode_agreement if plan else None,
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
