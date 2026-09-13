"""One application pipeline shared by JSON and SSE transports."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from time import perf_counter
from uuid import uuid4

from fastapi import HTTPException

from app.architecture.context import RequestContext
from app.architecture.orchestration import run_chat
from app.auth import ActorPrincipal
from app.call_limits import LimitCounter, request_call_limits
from app.chat_events import ChatCancelled, check_chat_cancelled
from app.chat_metrics import infer_standard_outcome
from app.config import get_llm_pricing
from app.conversation_lease import keep_turn_alive
from app.conversation_memory import prepare_memory
from app.conversation_store import (
    ConversationBusy,
    ConversationLease,
    ConversationNotFound,
    begin_turn,
    finish_turn,
)
from app.follow_up import build_follow_up_questions
from app.model_egress import bind_model_egress_tenant, is_model_egress_allowed, reset_model_egress_tenant
from app.models import ChatRequest, ChatResponse, TokenUsage


@dataclass(frozen=True)
class PreparedChat:
    request: ChatRequest
    principal: ActorPrincipal
    context: RequestContext
    exchange_id: str
    lease: ConversationLease | None = None

    @property
    def conversation_id(self) -> str | None:
        return self.lease.conversation_id if self.lease else None


def prepare_chat(request: ChatRequest, principal: ActorPrincipal) -> PreparedChat:
    if not request.question.strip():
        raise HTTPException(status_code=400, detail="Question cannot be empty.")
    if request.answer_mode == "api" and not is_model_egress_allowed(principal.tenant_id):
        raise HTTPException(status_code=403, detail="该工作区尚未获批向外部模型发送数据，请使用本地回答模式或联系管理员。")
    context = RequestContext.from_principal(principal)
    exchange_id = str(uuid4())
    lease = None
    if request.memory_mode != "none" or request.conversation_id:
        try:
            lease = begin_turn(request.conversation_id, tenant_id=context.tenant_id,
                               owner_id=context.owner_id, actor_user=principal.user_id, exchange_id=exchange_id)
        except ConversationNotFound as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        except ConversationBusy as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc
    return PreparedChat(request, principal, context, exchange_id, lease)


def execute_chat(prepared: PreparedChat, *, metric_recorder: Callable,
                 agentic_handler: Callable, standard_handler: Callable) -> ChatResponse:
    request, principal, context = prepared.request, prepared.principal, prepared.context
    lease = prepared.lease
    counter = LimitCounter(lease.limits) if lease else LimitCounter()
    started = perf_counter()
    egress_token = bind_model_egress_tenant(principal.tenant_id)
    completed = False
    try:
        with request_call_limits(counter), keep_turn_alive(lease):
            check_chat_cancelled()
            memory = prepare_memory(request.question, request.memory_mode, lease,
                                    allow_model=request.answer_mode != "local" and is_model_egress_allowed(principal.tenant_id)) if lease else None
            question = memory.question if memory else request.question
            scope = context.retrieval_scope(request.asset_ids) if principal.auth_mode == "jwt" or request.asset_ids else None
            response, plan = run_chat(question, workflow_mode=request.workflow_mode, answer_mode=request.answer_mode,
                                      retriever_mode=request.retriever_mode, actor_role=context.role,
                                      actor_user=context.actor_user, workspace_type=principal.workspace_type,
                                      retrieval_scope=scope, agentic_handler=agentic_handler, standard_handler=standard_handler)
            if memory:
                response.trace.insert(0, memory.trace)
                if memory.prompt_tokens or memory.completion_tokens:
                    usage = response.token_usage or TokenUsage()
                    usage.prompt_tokens += memory.prompt_tokens
                    usage.completion_tokens += memory.completion_tokens
                    usage.total_tokens += memory.prompt_tokens + memory.completion_tokens
                    usage.estimated_cost_usd += get_llm_pricing().estimate_cost(memory.prompt_tokens, memory.completion_tokens)
                    usage.source = "api_with_memory"
                    response.token_usage = usage
            response.conversation_id = prepared.conversation_id
            response.exchange_id = prepared.exchange_id
            summary = response.agent_summary
            outcome = "answered" if summary and summary.evidence_status in {"passed", "not_required"} else infer_standard_outcome(response)
            response.follow_up = build_follow_up_questions(
                question, response.sources, recent_questions=memory.recent_questions if memory else (),
            ) if outcome == "answered" else []
            check_chat_cancelled()
            if lease:
                finish_turn(lease, question=request.question, rewritten_question=question, response=response,
                            model_calls=counter.model_calls, tool_calls=counter.tool_calls,
                            summary=memory.summary, summary_through=memory.summary_through)
            completed = True
            log_id = metric_recorder(request=request, response=response, latency_ms=(perf_counter() - started) * 1000,
                                     outcome=outcome, principal=principal, plan=plan)
            if isinstance(log_id, int):
                response.log_id = log_id
            return response
    except BaseException as exc:
        if lease and not completed:
            try:
                finish_turn(lease, question=request.question, rewritten_question=request.question, response=None,
                            model_calls=counter.model_calls, tool_calls=counter.tool_calls)
            except ConversationBusy:
                pass  # A replacement worker owns the lease; never clear its reservation.
        if not isinstance(exc, ChatCancelled):
            metric_recorder(request=request, response=None, latency_ms=(perf_counter() - started) * 1000,
                            outcome="error", principal=principal, plan=None)
        if isinstance(exc, ConversationBusy):
            raise HTTPException(status_code=409, detail=str(exc)) from exc
        raise
    finally:
        reset_model_egress_tenant(egress_token)
