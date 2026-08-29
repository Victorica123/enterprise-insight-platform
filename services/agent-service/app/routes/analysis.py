from __future__ import annotations

import secrets
import uuid

from fastapi import APIRouter, Depends, HTTPException, Query, status

from app.analysis_models import (
    AnalysisAuditEvent, AnalysisConfirmationRequest, AnalysisCreateRequest,
    AnalysisSessionResponse, PublicationApprovalRequest,
)
from app.analysis_pipeline import run_six_stage_analysis
from app.analysis_store import (
    get_session, get_session_for_tenant, list_audit_events,
    list_pending_publications, list_sessions, save_session, utc_now,
)
from app.auth import ActorPrincipal, current_principal, require_write_role
from app.publication_service import (
    PublicationRuleError, approve_publication, request_publication,
)
from app.retrievers import RetrievalScope, load_chunks


router = APIRouter(prefix="/analysis", tags=["analysis"])


@router.post("/sessions", response_model=AnalysisSessionResponse, status_code=201)
def create_analysis_session(
    request: AnalysisCreateRequest,
    principal: ActorPrincipal = Depends(current_principal),
) -> AnalysisSessionResponse:
    require_write_role(principal.role)
    asset_ids = list(dict.fromkeys(request.asset_ids))
    scope = RetrievalScope(
        tenant_id=principal.tenant_id,
        owner_id=principal.retrieval_owner_id,
        asset_ids=tuple(asset_ids),
    )
    run = run_six_stage_analysis(request.objective, load_chunks(scope))
    now = utc_now()
    session = AnalysisSessionResponse(
        session_id=str(uuid.uuid4()), tenant_id=principal.tenant_id, owner_id=principal.user_id,
        objective=request.objective.strip(), asset_ids=asset_ids,
        status="WAITING_CONFIRMATION" if run.open_questions else "DRAFT_READY",
        current_stage=5 if run.open_questions else 6,
        resume_token=secrets.token_urlsafe(24) if run.open_questions else None,
        stages=run.stages, open_questions=run.open_questions, confirmations={}, prd=run.prd,
        created_at=now, updated_at=now,
    )
    save_session(session)
    return session


@router.get("/sessions", response_model=list[AnalysisSessionResponse])
def get_analysis_sessions(
    limit: int = Query(default=50, ge=1, le=100),
    principal: ActorPrincipal = Depends(current_principal),
) -> list[AnalysisSessionResponse]:
    return list_sessions(principal.tenant_id, principal.user_id, limit)


@router.get("/publication-queue", response_model=list[AnalysisSessionResponse])
def get_publication_queue(
    limit: int = Query(default=50, ge=1, le=100),
    principal: ActorPrincipal = Depends(current_principal),
) -> list[AnalysisSessionResponse]:
    require_write_role(principal.role)
    if principal.workspace_type != "team":
        return []
    return list_pending_publications(principal.tenant_id, principal.user_id, limit)


@router.get("/sessions/{session_id}", response_model=AnalysisSessionResponse)
def get_analysis_session(
    session_id: str,
    principal: ActorPrincipal = Depends(current_principal),
) -> AnalysisSessionResponse:
    return _require_session(session_id, principal)


@router.post("/sessions/{session_id}/confirm", response_model=AnalysisSessionResponse)
def confirm_analysis_session(
    session_id: str,
    request: AnalysisConfirmationRequest,
    principal: ActorPrincipal = Depends(current_principal),
) -> AnalysisSessionResponse:
    require_write_role(principal.role)
    existing = _require_session(session_id, principal)
    if existing.status != "WAITING_CONFIRMATION":
        raise HTTPException(status_code=409, detail="Analysis session is not waiting for confirmation.")
    if not existing.resume_token or not secrets.compare_digest(existing.resume_token, request.resume_token):
        raise HTTPException(status_code=409, detail="Invalid or stale analysis resume token.")
    answers = {**existing.confirmations, **{key: value.strip() for key, value in request.answers.items()}}
    scope = RetrievalScope(
        tenant_id=principal.tenant_id,
        owner_id=principal.retrieval_owner_id,
        asset_ids=tuple(existing.asset_ids),
    )
    run = run_six_stage_analysis(existing.objective, load_chunks(scope), answers)
    existing.confirmations = answers
    existing.stages = run.stages
    existing.open_questions = run.open_questions
    existing.prd = run.prd
    existing.status = "WAITING_CONFIRMATION" if run.open_questions else "DRAFT_READY"
    existing.current_stage = 5 if run.open_questions else 6
    existing.resume_token = secrets.token_urlsafe(24) if run.open_questions else None
    existing.updated_at = utc_now()
    save_session(existing)
    return existing


@router.post("/sessions/{session_id}/publication/request", response_model=AnalysisSessionResponse)
def request_prd_publication(
    session_id: str,
    principal: ActorPrincipal = Depends(current_principal),
) -> AnalysisSessionResponse:
    require_write_role(principal.role)
    existing = _require_session(session_id, principal)
    try:
        return request_publication(existing, principal)
    except PublicationRuleError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.detail) from exc


@router.post("/sessions/{session_id}/publication/approve", response_model=AnalysisSessionResponse)
def approve_prd_publication(
    session_id: str,
    request: PublicationApprovalRequest,
    principal: ActorPrincipal = Depends(current_principal),
) -> AnalysisSessionResponse:
    require_write_role(principal.role)
    existing = _require_tenant_session(session_id, principal)
    try:
        return approve_publication(existing, request, principal)
    except PublicationRuleError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.detail) from exc


@router.get("/sessions/{session_id}/audit", response_model=list[AnalysisAuditEvent])
def get_analysis_audit(
    session_id: str,
    principal: ActorPrincipal = Depends(current_principal),
) -> list[AnalysisAuditEvent]:
    _require_session(session_id, principal)
    return list_audit_events(session_id, principal.tenant_id)


def _require_session(session_id: str, principal: ActorPrincipal) -> AnalysisSessionResponse:
    session = get_session(session_id, principal.tenant_id, principal.user_id)
    if session is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Analysis session not found.")
    return session


def _require_tenant_session(session_id: str, principal: ActorPrincipal) -> AnalysisSessionResponse:
    session = get_session_for_tenant(session_id, principal.tenant_id)
    if session is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Analysis session not found.")
    return session
