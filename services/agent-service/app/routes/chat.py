"""JSON and SSE transports over the same authorized conversation pipeline."""

from functools import partial

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from starlette.concurrency import run_in_threadpool

from app.architecture.context import RequestContext
from app.architecture.conversation import (
    ConversationNotFound,
    execute_chat,
    get_conversation,
    prepare_chat,
    safe_record_chat_metric,
    stream_chat_events,
)
from app.architecture.conversation import (
    infer_standard_outcome as infer_standard_outcome,
)
from app.architecture.orchestration import answer_agentic_question, answer_question
from app.auth import ActorPrincipal, current_principal
from app.models import ChatRequest, ChatResponse

router = APIRouter(tags=["chat"])


def _runner(prepared):
    # Retain the original patch targets without exposing implementations to the route.
    return partial(execute_chat, prepared, metric_recorder=safe_record_chat_metric,
                   agentic_handler=answer_agentic_question, standard_handler=answer_question)


@router.post("/chat", response_model=ChatResponse, summary="Knowledge chat with optional conversation memory")
def chat(request: ChatRequest, principal: ActorPrincipal = Depends(current_principal)) -> ChatResponse:
    return _runner(prepare_chat(request, principal))()


@router.post("/chat/stream", summary="Stream progress, provisional text and the verified final response")
async def chat_stream(request: ChatRequest, principal: ActorPrincipal = Depends(current_principal)):
    prepared = await run_in_threadpool(prepare_chat, request, principal)
    return StreamingResponse(
        stream_chat_events(_runner(prepared), conversation_id=prepared.conversation_id, exchange_id=prepared.exchange_id),
        media_type="text/event-stream", headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@router.get("/conversations/{conversation_id}", summary="Read an authorized conversation")
def conversation_history(conversation_id: str, principal: ActorPrincipal = Depends(current_principal)):
    context = RequestContext.from_principal(principal)
    try:
        return get_conversation(conversation_id, tenant_id=context.tenant_id, owner_id=context.owner_id)
    except ConversationNotFound as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
