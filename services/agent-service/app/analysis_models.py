from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field, model_validator


AnalysisStatus = Literal["RUNNING", "WAITING_CONFIRMATION", "DRAFT_READY", "FAILED"]


class AnalysisCreateRequest(BaseModel):
    objective: str = Field(min_length=3, max_length=1000)
    asset_ids: list[str] = Field(default_factory=list, max_length=50)


class AnalysisConfirmationRequest(BaseModel):
    resume_token: str = Field(min_length=16, max_length=128)
    answers: dict[str, str] = Field(min_length=1, max_length=20)


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
    publication_status: Literal["DRAFT"] = "DRAFT"


class AnalysisSessionResponse(BaseModel):
    session_id: str
    tenant_id: str
    owner_id: str
    objective: str
    asset_ids: list[str]
    status: AnalysisStatus
    current_stage: int = Field(ge=1, le=6)
    resume_token: str | None = None
    stages: list[AnalysisStageResult]
    open_questions: list[OpenQuestion]
    confirmations: dict[str, str]
    prd: PrdDraft | None = None
    created_at: datetime
    updated_at: datetime
