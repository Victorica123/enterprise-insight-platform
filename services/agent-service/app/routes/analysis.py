from __future__ import annotations

import secrets
import uuid

from fastapi import APIRouter, Depends, HTTPException, Query, status

from app.analysis_models import (
    ActionItemTicketDraftResponse, AnalysisAuditEvent, AnalysisConfirmationRequest,
    AnalysisCreateRequest, AnalysisSessionResponse, KnowledgeCandidate,
    KnowledgeCandidateDecisionRequest, KnowledgeLifecycleCreateRequest,
    KnowledgeLifecycleDecisionRequest, KnowledgeLifecycleRequest, PublicationApprovalRequest,
    PublicationDeliverables,
)
from app.architecture.execution import execute_tool, resume_six_stage_analysis, run_six_stage_analysis
from app.architecture.governance import (
    get_evidence_snapshot, get_session, get_session_for_tenant, list_audit_events,
    list_pending_publications, list_sessions, save_session, transition_confirmation, utc_now,
    PublicationRuleError, approve_publication, request_publication,
    decide_knowledge_candidate, decide_knowledge_lifecycle, get_action_item,
    get_publication_deliverables, mark_action_ticket_pending, request_knowledge_lifecycle,
)
from app.architecture.retrieval import build_analysis_evidence_snapshot, EvidenceProvenanceError, RetrievalScope
from app.auth import ActorPrincipal, current_principal, require_write_role


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
    snapshot = build_analysis_evidence_snapshot(request.objective, scope)
    run = run_six_stage_analysis(request.objective, list(snapshot.chunks))
    now = utc_now()
    session = AnalysisSessionResponse(
        session_id=str(uuid.uuid4()), tenant_id=principal.tenant_id, owner_id=principal.user_id,
        objective=request.objective.strip(), asset_ids=asset_ids,
        status="WAITING_CONFIRMATION" if run.open_questions else "DRAFT_READY",
        current_stage=5 if run.open_questions else 6,
        checkpoint_version=1,
        evidence_revision=snapshot.revision,
        evidence_snapshot_sha256=snapshot.sha256,
        retrieval_mode="hybrid",
        resume_token=secrets.token_urlsafe(24) if run.open_questions else None,
        stages=run.stages, open_questions=run.open_questions, confirmations={}, prd=run.prd,
        created_at=now, updated_at=now,
    )
    save_session(session, snapshot)
    return session


@router.get("/sessions", response_model=list[AnalysisSessionResponse])
def get_analysis_sessions(
    limit: int = Query(default=50, ge=1, le=100),
    principal: ActorPrincipal = Depends(current_principal),
) -> list[AnalysisSessionResponse]:
    return list_sessions(
        principal.tenant_id, principal.resource_owner_id, limit,
    )


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
    return (
        _require_tenant_session(session_id, principal)
        if principal.workspace_type == "team"
        else _require_session(session_id, principal)
    )


@router.post("/sessions/{session_id}/confirm", response_model=AnalysisSessionResponse)
def confirm_analysis_session(
    session_id: str,
    request: AnalysisConfirmationRequest,
    principal: ActorPrincipal = Depends(current_principal),
) -> AnalysisSessionResponse:
    require_write_role(principal.role)
    existing = (
        _require_tenant_session(session_id, principal)
        if principal.workspace_type == "team"
        else _require_session(session_id, principal)
    )
    if existing.status != "WAITING_CONFIRMATION":
        raise HTTPException(status_code=409, detail="Analysis session is not waiting for confirmation.")
    if not existing.resume_token or not secrets.compare_digest(existing.resume_token, request.resume_token):
        raise HTTPException(status_code=409, detail="Invalid or stale analysis resume token.")
    answers = {**existing.confirmations, **{key: value.strip() for key, value in request.answers.items()}}
    snapshot = get_evidence_snapshot(existing.session_id, existing.tenant_id)
    run = resume_six_stage_analysis(
        existing.objective, list(snapshot.chunks), existing.stages, answers,
    )
    existing.confirmations = answers
    existing.stages = run.stages
    existing.open_questions = run.open_questions
    existing.prd = run.prd
    existing.status = "WAITING_CONFIRMATION" if run.open_questions else "DRAFT_READY"
    existing.current_stage = 5 if run.open_questions else 6
    existing.checkpoint_version += 1
    existing.resume_token = secrets.token_urlsafe(24) if run.open_questions else None
    existing.updated_at = utc_now()
    if not transition_confirmation(existing, expected_resume_token=request.resume_token):
        raise HTTPException(status_code=409, detail="Invalid or stale analysis resume token.")
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
    if principal.workspace_type == "team":
        _require_tenant_session(session_id, principal)
    else:
        _require_session(session_id, principal)
    return list_audit_events(session_id, principal.tenant_id)


@router.get(
    "/sessions/{session_id}/deliverables",
    response_model=PublicationDeliverables,
)
def get_published_deliverables(
    session_id: str,
    principal: ActorPrincipal = Depends(current_principal),
) -> PublicationDeliverables:
    session = (
        _require_tenant_session(session_id, principal)
        if principal.workspace_type == "team"
        else _require_session(session_id, principal)
    )
    if session.status != "PUBLISHED":
        raise HTTPException(status_code=409, detail="The PRD has not been published.")
    deliverables = get_publication_deliverables(session_id, principal.tenant_id)
    if deliverables is None:
        raise HTTPException(status_code=404, detail="Published deliverables not found.")
    return deliverables


@router.post(
    "/sessions/{session_id}/knowledge-candidates/{candidate_id}/decision",
    response_model=KnowledgeCandidate,
)
def decide_published_knowledge_candidate(
    session_id: str,
    candidate_id: str,
    request: KnowledgeCandidateDecisionRequest,
    principal: ActorPrincipal = Depends(current_principal),
) -> KnowledgeCandidate:
    require_write_role(principal.role)
    session = _require_tenant_session(session_id, principal)
    if session.status != "PUBLISHED":
        raise HTTPException(status_code=409, detail="The PRD has not been published.")
    if principal.workspace_type == "personal":
        if principal.user_id != session.owner_id or principal.role != "admin":
            raise HTTPException(status_code=403, detail="Only the personal workspace owner can decide knowledge candidates.")
    elif principal.user_id == session.owner_id:
        raise HTTPException(status_code=403, detail="Team knowledge publication requires a different reviewer.")
    bundle = get_publication_deliverables(session_id, principal.tenant_id)
    if bundle is None or not any(item.candidate_id == candidate_id for item in bundle.knowledge_candidates):
        raise HTTPException(status_code=404, detail="Knowledge candidate not found.")
    try:
        decided = decide_knowledge_candidate(
            candidate_id,
            tenant_id=principal.tenant_id,
            actor_id=principal.user_id,
            approved=request.approved,
            decided_at=utc_now(),
            evidence_owner_id=principal.user_id if principal.workspace_type == "personal" else None,
        )
    except EvidenceProvenanceError as exc:
        raise HTTPException(status_code=409, detail=f"Evidence provenance validation failed: {exc}") from exc
    if decided is None:
        raise HTTPException(status_code=409, detail="Knowledge candidate was already decided.")
    return decided


@router.post(
    "/sessions/{session_id}/knowledge-candidates/{candidate_id}/lifecycle-requests",
    response_model=KnowledgeLifecycleRequest,
    status_code=201,
)
def create_knowledge_lifecycle_request(
    session_id: str,
    candidate_id: str,
    request: KnowledgeLifecycleCreateRequest,
    principal: ActorPrincipal = Depends(current_principal),
) -> KnowledgeLifecycleRequest:
    require_write_role(principal.role)
    session = _require_tenant_session(session_id, principal)
    if session.status != "PUBLISHED":
        raise HTTPException(status_code=409, detail="The PRD has not been published.")
    if principal.workspace_type == "personal" and (
        principal.user_id != session.owner_id or principal.role != "admin"
    ):
        raise HTTPException(status_code=403, detail="Only the personal workspace owner can govern knowledge.")
    bundle = get_publication_deliverables(session_id, principal.tenant_id)
    candidate = next(
        (item for item in bundle.knowledge_candidates if item.candidate_id == candidate_id),
        None,
    ) if bundle else None
    if candidate is None:
        raise HTTPException(status_code=404, detail="Knowledge candidate not found.")
    try:
        created = request_knowledge_lifecycle(
            candidate_id,
            tenant_id=principal.tenant_id,
            actor_id=principal.user_id,
            action=request.action,
            reason=request.reason,
            replacement_statement=request.replacement_statement,
            replacement_evidence=[item.model_dump(mode="json") for item in request.replacement_evidence],
            requested_at=utc_now(),
            evidence_owner_id=principal.user_id if principal.workspace_type == "personal" else None,
        )
    except EvidenceProvenanceError as exc:
        raise HTTPException(status_code=409, detail=f"Evidence provenance validation failed: {exc}") from exc
    if created is None:
        raise HTTPException(
            status_code=409,
            detail="Knowledge is not active, has a pending lifecycle request, or the replacement is unchanged.",
        )
    return created


@router.post(
    "/sessions/{session_id}/knowledge-candidates/{candidate_id}/lifecycle-requests/{request_id}/decision",
    response_model=KnowledgeLifecycleRequest,
)
def decide_knowledge_lifecycle_request(
    session_id: str,
    candidate_id: str,
    request_id: str,
    request: KnowledgeLifecycleDecisionRequest,
    principal: ActorPrincipal = Depends(current_principal),
) -> KnowledgeLifecycleRequest:
    require_write_role(principal.role)
    session = _require_tenant_session(session_id, principal)
    if session.status != "PUBLISHED":
        raise HTTPException(status_code=409, detail="The PRD has not been published.")
    bundle = get_publication_deliverables(session_id, principal.tenant_id)
    lifecycle = next(
        (
            item for item in bundle.knowledge_lifecycle_requests
            if item.request_id == request_id and item.candidate_id == candidate_id
        ),
        None,
    ) if bundle else None
    if lifecycle is None:
        raise HTTPException(status_code=404, detail="Knowledge lifecycle request not found.")
    if principal.workspace_type == "personal":
        if principal.user_id != session.owner_id or principal.role != "admin":
            raise HTTPException(status_code=403, detail="Only the personal workspace owner can govern knowledge.")
    elif lifecycle.requested_by == principal.user_id:
        raise HTTPException(status_code=403, detail="Team knowledge lifecycle requires a different reviewer.")
    try:
        decided = decide_knowledge_lifecycle(
            request_id,
            candidate_id=candidate_id,
            tenant_id=principal.tenant_id,
            actor_id=principal.user_id,
            approved=request.approved,
            decided_at=utc_now(),
            evidence_owner_id=principal.user_id if principal.workspace_type == "personal" else None,
        )
    except EvidenceProvenanceError as exc:
        raise HTTPException(status_code=409, detail=f"Evidence provenance validation failed: {exc}") from exc
    if decided is None:
        raise HTTPException(status_code=409, detail="Knowledge lifecycle request was already decided or is stale.")
    return decided


@router.post(
    "/sessions/{session_id}/action-items/{action_item_id}/ticket-draft",
    response_model=ActionItemTicketDraftResponse,
)
def create_action_item_ticket_draft(
    session_id: str,
    action_item_id: str,
    principal: ActorPrincipal = Depends(current_principal),
) -> ActionItemTicketDraftResponse:
    require_write_role(principal.role)
    session = (
        _require_tenant_session(session_id, principal)
        if principal.workspace_type == "team"
        else _require_session(session_id, principal)
    )
    if session.status != "PUBLISHED":
        raise HTTPException(status_code=409, detail="The PRD has not been published.")
    item = get_action_item(action_item_id, principal.tenant_id)
    if item is None or item.session_id != session_id or (
        principal.workspace_type != "team" and item.owner_id != principal.user_id
    ):
        raise HTTPException(status_code=404, detail="Action item not found.")
    if item.status != "DRAFT":
        if item.pending_action_id:
            return ActionItemTicketDraftResponse(
                action_item=item, pending_action_id=item.pending_action_id,
            )
        raise HTTPException(status_code=409, detail="Action item cannot enter ticket approval.")
    result = execute_tool(
        "create_ticket",
        {
            "title": item.title,
            "description": item.description,
            "priority": item.priority,
            "source_document_ids": list(dict.fromkeys(
                evidence.document_id for evidence in item.evidence
            )),
        },
        actor_role=principal.role,
        actor_user=principal.actor_user,
        tenant_id=principal.tenant_id,
        owner_id=principal.user_id,
        workspace_type=principal.workspace_type,
    )
    if not result.success or not result.pending_action_id:
        raise HTTPException(
            status_code=400,
            detail=result.result.get("error", "Ticket draft could not be created."),
        )
    updated = mark_action_ticket_pending(
        action_item_id,
        tenant_id=principal.tenant_id,
        pending_action_id=result.pending_action_id,
        updated_at=utc_now(),
    )
    if updated is None:
        current = get_action_item(action_item_id, principal.tenant_id)
        if current is not None and current.pending_action_id:
            return ActionItemTicketDraftResponse(
                action_item=current, pending_action_id=current.pending_action_id,
            )
        raise HTTPException(status_code=409, detail="Action item was changed by another request.")
    return ActionItemTicketDraftResponse(
        action_item=updated, pending_action_id=result.pending_action_id,
    )


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
