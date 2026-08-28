"""聊天端点：编排 standard/agentic RAG，并记录指标与请求日志。"""
import logging
from time import perf_counter

from fastapi import APIRouter, Header, HTTPException

from app.agentic_rag import answer_agentic_question
from app.auth import normalize_actor_user, validate_actor_role
from app.database import record_chat_log, record_chat_metric
from app.models import ChatRequest, ChatResponse
from app.rag import answer_question


logger = logging.getLogger(__name__)

router = APIRouter(tags=["chat"])


@router.post("/chat", response_model=ChatResponse, summary="知识库问答（standard / agentic）",
             responses={200: {"description": "回答 + 来源证据 + 执行轨迹 + token 用量 + 待审批操作"}})
def chat(
    request: ChatRequest,
    x_user_role: str = Header(default="viewer"),
    x_user_id: str = Header(default=""),
) -> ChatResponse:
    if not request.question.strip():
        raise HTTPException(status_code=400, detail="Question cannot be empty.")

    actor_role = validate_actor_role(x_user_role)
    actor_user = normalize_actor_user(x_user_id)
    started_at = perf_counter()
    try:
        if request.workflow_mode == "agentic":
            response = answer_agentic_question(
                request.question,
                answer_mode=request.answer_mode,
                retriever_mode=request.retriever_mode,
                actor_role=actor_role,
                actor_user=actor_user,
            )
        else:
            response = answer_question(
                request.question,
                answer_mode=request.answer_mode,
                retriever_mode=request.retriever_mode,
            )
    except Exception:
        logger.exception("chat_failed workflow=%s mode=%s", request.workflow_mode, request.answer_mode)
        safe_record_chat_metric(
            request=request,
            response=None,
            latency_ms=(perf_counter() - started_at) * 1000,
            outcome="error",
        )
        raise

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
    return "refused" if any(marker in response.answer for marker in refused_markers) else "answered"


def safe_record_chat_metric(
    *,
    request: ChatRequest,
    response: ChatResponse | None,
    latency_ms: float,
    outcome: str,
) -> int:
    """记录指标 + 请求日志（含 token 成本），返回日志 ID 供反馈使用。"""
    try:
        summary = response.agent_summary if response else None
        usage = response.token_usage if response else None
        answer_status = "error"
        if response:
            answer_step = next((step for step in reversed(response.trace) if step.name == "answer"), None)
            answer_status = answer_step.status if answer_step else "not_generated"

        record_chat_metric(
            workflow_mode=request.workflow_mode,
            answer_mode=request.answer_mode,
            retriever_mode=request.retriever_mode,
            intent=summary.intent if summary else "standard",
            complexity=summary.complexity if summary else "standard",
            retrieval_rounds=summary.retrieval_rounds if summary else 1,
            query_count=len(summary.queries) if summary else 1,
            evidence_status=summary.evidence_status if summary else ("passed" if outcome == "answered" else "refused"),
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
        )
    except Exception:
        logger.exception("Failed to record chat metric")
        return 0
