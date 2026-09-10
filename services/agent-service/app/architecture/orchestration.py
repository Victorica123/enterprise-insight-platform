"""Conversation orchestration boundary (the panorama's 编排中心).

Routing, query planning, agentic RAG and standard RAG still use the proven
implementations in ``agentic_rag`` and ``rag``.  This module is the stable
application-facing entry point and keeps HTTP handlers unaware of those
implementation details.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable

from app.agentic_rag import answer_agentic_question
from app.models import ChatResponse
from app.rag import answer_question
from app.retrievers import RetrievalScope


@dataclass(frozen=True)
class ConversationInput:
    question: str
    workflow_mode: str
    answer_mode: str
    retriever_mode: str
    actor_role: str = "operator"
    actor_user: str = "anonymous"
    workspace_type: str = "team"
    retrieval_scope: RetrievalScope | None = None


class ConversationOrchestrator:
    """Select exactly one deterministic workflow for a conversation turn."""

    def __init__(
        self,
        *,
        agentic_handler: Callable[..., ChatResponse] = answer_agentic_question,
        standard_handler: Callable[..., ChatResponse] = answer_question,
    ) -> None:
        # Injection keeps this boundary observable by compatibility tests and
        # alternate runtimes without exposing persistence implementation.
        self._agentic_handler = agentic_handler
        self._standard_handler = standard_handler

    def answer(self, request: ConversationInput) -> ChatResponse:
        if request.workflow_mode == "agentic":
            kwargs = dict(
                answer_mode=request.answer_mode,
                retriever_mode=request.retriever_mode,
                actor_role=request.actor_role,
                actor_user=request.actor_user,
                workspace_type=request.workspace_type,
            )
            if request.retrieval_scope is not None:
                kwargs["retrieval_scope"] = request.retrieval_scope
            return self._agentic_handler(
                request.question,
                **kwargs,
            )
        kwargs = dict(
            answer_mode=request.answer_mode,
            retriever_mode=request.retriever_mode,
        )
        if request.retrieval_scope is not None:
            kwargs["scope"] = request.retrieval_scope
        return self._standard_handler(
            request.question,
            **kwargs,
        )


def answer_chat(
    question: str,
    *,
    workflow_mode: str,
    answer_mode: str,
    retriever_mode: str,
    actor_role: str,
    actor_user: str,
    workspace_type: str,
    retrieval_scope: RetrievalScope | None = None,
    agentic_handler: Callable[..., ChatResponse] = answer_agentic_question,
    standard_handler: Callable[..., ChatResponse] = answer_question,
) -> ChatResponse:
    """Compatibility-friendly function used by the chat route."""
    return ConversationOrchestrator(
        agentic_handler=agentic_handler,
        standard_handler=standard_handler,
    ).answer(
        ConversationInput(
            question=question,
            workflow_mode=workflow_mode,
            answer_mode=answer_mode,
            retriever_mode=retriever_mode,
            actor_role=actor_role,
            actor_user=actor_user,
            workspace_type=workspace_type,
            retrieval_scope=retrieval_scope,
        )
    )
