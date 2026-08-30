from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field, model_validator


AnalysisStatus = Literal[
    "RUNNING", "WAITING_CONFIRMATION", "DRAFT_READY",
    "PUBLISH_PENDING", "PUBLISHED", "FAILED",
]


class AnalysisCreateRequest(BaseModel):
    objective: str = Field(min_length=3, max_length=1000)
    asset_ids: list[str] = Field(default_factory=list, max_length=50)


class AnalysisConfirmationRequest(BaseModel):
    resume_token: str = Field(min_length=16, max_length=128)
    answers: dict[str, str] = Field(min_length=1, max_length=20)


class PublicationApprovalRequest(BaseModel):
    request_id: str = Field(min_length=16, max_length=64)
    approval_token: str = Field(min_length=16, max_length=128)
    confirmation: Literal["PUBLISH"]


class EvidenceRef(BaseModel):
    source_type: Literal["document", "video"]
    document_id: str
    filename: str
    chunk_index: int
    excerpt: str
    asset_id: str | None = None
    segment_id: str | None = None
    start_ms: int | None = Field(default=None, ge=0)
    end_ms: int | None = Field(default=None, ge=0)
    speaker: str | None = None

    @model_validator(mode="after")
    def validate_video_location(self) -> "EvidenceRef":
        if self.source_type == "video":
            if not self.asset_id or not self.segment_id or self.start_ms is None or self.end_ms is None:
                raise ValueError("video evidence requires asset, segment and time range")
            if self.end_ms < self.start_ms:
                raise ValueError("video evidence end_ms must not precede start_ms")
        return self


class OpenQuestion(BaseModel):
    question_id: str
    question: str
    reason: str
    required: bool = True


class AnalysisStageResult(BaseModel):
    stage: Literal["intent", "stakeholders", "domain", "risks", "convergence", "prd"]
    status: Literal["COMPLETED", "WAITING_CONFIRMATION"]
    summary: str
    findings: list[str] = Field(default_factory=list)
    evidence: list[EvidenceRef] = Field(default_factory=list)
    open_questions: list[OpenQuestion] = Field(default_factory=list)


class PrdRequirement(BaseModel):
    requirement_id: str
    title: str
    description: str
    acceptance_criteria: list[str]
    evidence: list[EvidenceRef]
    assumptions: list[str] = Field(default_factory=list)


class PrdDraft(BaseModel):
    title: str
    executive_summary: str
    goals: list[str]
    stakeholders: list[str]
    requirements: list[PrdRequirement]
    risks: list[str]
    open_questions: list[OpenQuestion] = Field(default_factory=list)
    publication_status: Literal["DRAFT", "PUBLISH_PENDING", "PUBLISHED"] = "DRAFT"


class PublicationApproval(BaseModel):
    request_id: str
    policy: Literal["OWNER_RECONFIRMATION", "FOUR_EYES"]
    status: Literal["PENDING", "APPROVED"]
    requested_by: str
    requested_at: datetime
    approval_token: str | None = None
    approved_by: str | None = None
    approved_at: datetime | None = None


class AnalysisAuditEvent(BaseModel):
    event_id: str
    session_id: str
    action: Literal["PUBLICATION_REQUESTED", "PUBLICATION_APPROVED"]
    actor_id: str
    actor_role: str
    details: dict[str, str] = Field(default_factory=dict)
    created_at: datetime


class AnalysisSessionResponse(BaseModel):
    session_id: str
    tenant_id: str
    owner_id: str
    objective: str
    asset_ids: list[str]
    status: AnalysisStatus
    current_stage: int = Field(ge=1, le=6)
    checkpoint_version: int = Field(default=1, ge=1)
    evidence_revision: int = Field(default=0, ge=0)
    evidence_snapshot_sha256: str = Field(min_length=64, max_length=64)
    retrieval_mode: Literal["hybrid"] = "hybrid"
    resume_token: str | None = None
    stages: list[AnalysisStageResult]
    open_questions: list[OpenQuestion]
    confirmations: dict[str, str]
    prd: PrdDraft | None = None
    publication: PublicationApproval | None = None
    created_at: datetime
    updated_at: datetime


class PublishedPrdVersion(BaseModel):
    version_id: str
    session_id: str
    tenant_id: str
    owner_id: str
    version_number: int = Field(ge=1)
    content_sha256: str
    prd: PrdDraft
    published_by: str
    published_at: datetime


class KnowledgeCandidate(BaseModel):
    candidate_id: str
    session_id: str
    version_id: str
    tenant_id: str
    owner_id: str
    requirement_id: str
    statement: str
    evidence: list[EvidenceRef]
    status: Literal["PENDING", "APPROVED", "REJECTED"] = "PENDING"
    created_by: str
    created_at: datetime
    decided_by: str | None = None
    decided_at: datetime | None = None
    knowledge_document_id: str | None = None
    knowledge_content_sha256: str | None = None
    knowledge_published_at: datetime | None = None
    knowledge_status: Literal["NONE", "ACTIVE", "REVOKED"] = "NONE"
    active_knowledge_version_id: str | None = None
    knowledge_version_number: int = Field(default=0, ge=0)
    pending_lifecycle_request_id: str | None = None


class GovernedKnowledgeVersion(BaseModel):
    knowledge_version_id: str
    candidate_id: str
    tenant_id: str
    owner_id: str
    version_number: int = Field(ge=1)
    statement: str
    evidence: list[EvidenceRef] = Field(min_length=1)
    document_id: str
    content_sha256: str
    status: Literal["ACTIVE", "SUPERSEDED", "REVOKED"]
    predecessor_version_id: str | None = None
    successor_version_id: str | None = None
    approved_by: str
    approved_at: datetime
    invalidated_by: str | None = None
    invalidated_at: datetime | None = None
    invalidation_reason: str | None = None


class KnowledgeLifecycleRequest(BaseModel):
    request_id: str
    candidate_id: str
    tenant_id: str
    owner_id: str
    action: Literal["REVOKE", "SUPERSEDE"]
    reason: str
    replacement_statement: str | None = None
    replacement_evidence: list[EvidenceRef] = Field(default_factory=list)
    status: Literal["PENDING", "APPROVED", "REJECTED"] = "PENDING"
    requested_by: str
    requested_at: datetime
    decided_by: str | None = None
    decided_at: datetime | None = None
    resulting_version_id: str | None = None


class KnowledgeLifecycleCreateRequest(BaseModel):
    action: Literal["REVOKE", "SUPERSEDE"]
    reason: str = Field(min_length=3, max_length=1000)
    replacement_statement: str | None = Field(default=None, max_length=4000)
    replacement_evidence: list[EvidenceRef] = Field(default_factory=list, max_length=50)

    @model_validator(mode="after")
    def validate_supersession(self) -> "KnowledgeLifecycleCreateRequest":
        if self.action == "SUPERSEDE":
            if not self.replacement_statement or len(self.replacement_statement.strip()) < 3:
                raise ValueError("supersede requires a replacement statement")
            if not self.replacement_evidence:
                raise ValueError("supersede requires evidence")
        return self


class KnowledgeLifecycleDecisionRequest(BaseModel):
    approved: bool


class ActionItemDraft(BaseModel):
    action_item_id: str
    session_id: str
    version_id: str
    tenant_id: str
    owner_id: str
    requirement_id: str
    title: str
    description: str
    priority: Literal["low", "medium", "high", "critical"] = "medium"
    evidence: list[EvidenceRef]
    status: Literal[
        "DRAFT", "TICKET_PENDING_APPROVAL", "TICKET_CREATED",
        "TICKET_REJECTED", "TICKET_FAILED",
    ] = "DRAFT"
    pending_action_id: str | None = None
    ticket_id: str | None = None
    created_at: datetime
    updated_at: datetime


class PublicationDeliverables(BaseModel):
    version: PublishedPrdVersion
    knowledge_candidates: list[KnowledgeCandidate]
    knowledge_versions: list[GovernedKnowledgeVersion] = Field(default_factory=list)
    knowledge_lifecycle_requests: list[KnowledgeLifecycleRequest] = Field(default_factory=list)
    action_items: list[ActionItemDraft]


class KnowledgeCandidateDecisionRequest(BaseModel):
    approved: bool


class ActionItemTicketDraftResponse(BaseModel):
    action_item: ActionItemDraft
    pending_action_id: str
