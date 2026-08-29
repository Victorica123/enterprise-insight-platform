from __future__ import annotations

import secrets
import uuid

from app.analysis_models import (
    AnalysisAuditEvent,
    AnalysisSessionResponse,
    PublicationApproval,
    PublicationApprovalRequest,
)
from app.analysis_store import transition_session, utc_now
from app.auth import ActorPrincipal, WRITE_ROLES
from app.publication_artifacts import build_publication_deliverables


class PublicationRuleError(Exception):
    def __init__(self, status_code: int, detail: str) -> None:
        super().__init__(detail)
        self.status_code = status_code
        self.detail = detail


def request_publication(
    session: AnalysisSessionResponse,
    principal: ActorPrincipal,
) -> AnalysisSessionResponse:
    if session.owner_id != principal.user_id:
        raise PublicationRuleError(404, "Analysis session not found.")
    if session.status != "DRAFT_READY" or session.prd is None:
        raise PublicationRuleError(409, "Only a ready PRD draft can request publication.")
    if principal.workspace_type == "personal" and principal.role != "admin":
        raise PublicationRuleError(403, "Personal workspace publication requires its owner.")
    if principal.workspace_type == "team" and principal.role not in WRITE_ROLES:
        raise PublicationRuleError(403, "Write permission is required to request publication.")

    now = utc_now()
    policy = "OWNER_RECONFIRMATION" if principal.workspace_type == "personal" else "FOUR_EYES"
    request_id = str(uuid.uuid4())
    session.status = "PUBLISH_PENDING"
    session.prd.publication_status = "PUBLISH_PENDING"
    session.publication = PublicationApproval(
        request_id=request_id,
        policy=policy,
        status="PENDING",
        requested_by=principal.user_id,
        requested_at=now,
        approval_token=secrets.token_urlsafe(24),
    )
    session.updated_at = now
    event = AnalysisAuditEvent(
        event_id=str(uuid.uuid4()),
        session_id=session.session_id,
        action="PUBLICATION_REQUESTED",
        actor_id=principal.user_id,
        actor_role=principal.role,
        details={"policy": policy, "request_id": request_id},
        created_at=now,
    )
    if not transition_session(session, expected_status="DRAFT_READY", audit_event=event):
        raise PublicationRuleError(409, "The PRD publication state changed; refresh and retry.")
    return session


def approve_publication(
    session: AnalysisSessionResponse,
    request: PublicationApprovalRequest,
    principal: ActorPrincipal,
) -> AnalysisSessionResponse:
    publication = session.publication
    if session.status != "PUBLISH_PENDING" or publication is None or publication.status != "PENDING":
        raise PublicationRuleError(409, "The PRD is not awaiting publication approval.")
    if publication.request_id != request.request_id:
        raise PublicationRuleError(409, "Invalid or stale publication request.")
    if not publication.approval_token or not secrets.compare_digest(
        publication.approval_token, request.approval_token,
    ):
        raise PublicationRuleError(409, "Invalid or stale publication approval token.")

    if publication.policy == "OWNER_RECONFIRMATION":
        if principal.workspace_type != "personal":
            raise PublicationRuleError(409, "Workspace publication policy changed; request again.")
        if principal.role != "admin" or principal.user_id != session.owner_id:
            raise PublicationRuleError(403, "Only the personal workspace owner can confirm publication.")
    else:
        if principal.workspace_type != "team":
            raise PublicationRuleError(409, "Workspace publication policy changed; request again.")
        if principal.role not in WRITE_ROLES:
            raise PublicationRuleError(403, "Write permission is required to approve publication.")
        if principal.user_id == publication.requested_by:
            raise PublicationRuleError(403, "Team publication requires a different approver.")

    now = utc_now()
    publication.status = "APPROVED"
    publication.approved_by = principal.user_id
    publication.approved_at = now
    publication.approval_token = None
    session.status = "PUBLISHED"
    if session.prd is None:
        raise PublicationRuleError(409, "The PRD draft no longer exists.")
    session.prd.publication_status = "PUBLISHED"
    session.updated_at = now
    event = AnalysisAuditEvent(
        event_id=str(uuid.uuid4()),
        session_id=session.session_id,
        action="PUBLICATION_APPROVED",
        actor_id=principal.user_id,
        actor_role=principal.role,
        details={
            "policy": publication.policy,
            "request_id": publication.request_id,
            "requested_by": publication.requested_by,
        },
        created_at=now,
    )
    deliverables = build_publication_deliverables(
        session, published_by=principal.user_id, published_at=now,
    )
    if not transition_session(
        session,
        expected_status="PUBLISH_PENDING",
        audit_event=event,
        publication_deliverables=deliverables,
    ):
        raise PublicationRuleError(409, "The PRD was already decided by another request.")
    return session
