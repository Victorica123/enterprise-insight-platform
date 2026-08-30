import { agentRequest } from "./api";

export type AnalysisEvidence = {
  source_type: "document" | "video";
  document_id: string;
  filename: string;
  chunk_index: number;
  excerpt: string;
  asset_id?: string | null;
  segment_id?: string | null;
  start_ms?: number | null;
  end_ms?: number | null;
  speaker?: string | null;
};

export type AnalysisQuestion = { question_id: string; question: string; reason: string; required: boolean };
export type AnalysisStage = {
  stage: "intent" | "stakeholders" | "domain" | "risks" | "convergence" | "prd";
  status: "COMPLETED" | "WAITING_CONFIRMATION";
  summary: string;
  findings: string[];
  evidence: AnalysisEvidence[];
  open_questions: AnalysisQuestion[];
};
export type PrdDraft = {
  title: string;
  executive_summary: string;
  goals: string[];
  stakeholders: string[];
  requirements: Array<{
    requirement_id: string;
    title: string;
    description: string;
    acceptance_criteria: string[];
    evidence: AnalysisEvidence[];
    assumptions: string[];
  }>;
  risks: string[];
  open_questions: AnalysisQuestion[];
  publication_status: "DRAFT" | "PUBLISH_PENDING" | "PUBLISHED";
};
export type PublicationApproval = {
  request_id: string;
  policy: "OWNER_RECONFIRMATION" | "FOUR_EYES";
  status: "PENDING" | "APPROVED";
  requested_by: string;
  requested_at: string;
  approval_token: string | null;
  approved_by: string | null;
  approved_at: string | null;
};
export type AnalysisAuditEvent = {
  event_id: string;
  session_id: string;
  action: "PUBLICATION_REQUESTED" | "PUBLICATION_APPROVED";
  actor_id: string;
  actor_role: string;
  details: Record<string, string>;
  created_at: string;
};
export type AnalysisSession = {
  session_id: string;
  tenant_id: string;
  owner_id: string;
  objective: string;
  asset_ids: string[];
  status: "RUNNING" | "WAITING_CONFIRMATION" | "DRAFT_READY" | "PUBLISH_PENDING" | "PUBLISHED" | "FAILED";
  current_stage: number;
  checkpoint_version: number;
  evidence_revision: number;
  evidence_snapshot_sha256: string;
  retrieval_mode: "hybrid";
  resume_token: string | null;
  stages: AnalysisStage[];
  open_questions: AnalysisQuestion[];
  confirmations: Record<string, string>;
  prd: PrdDraft | null;
  publication: PublicationApproval | null;
  created_at: string;
  updated_at: string;
};

export type KnowledgeCandidate = {
  candidate_id: string;
  session_id: string;
  version_id: string;
  owner_id: string;
  requirement_id: string;
  statement: string;
  evidence: AnalysisEvidence[];
  status: "PENDING" | "APPROVED" | "REJECTED";
  created_by: string;
  created_at: string;
  decided_by: string | null;
  decided_at: string | null;
  knowledge_document_id: string | null;
  knowledge_content_sha256: string | null;
  knowledge_published_at: string | null;
};

export type ActionItemDraft = {
  action_item_id: string;
  session_id: string;
  version_id: string;
  owner_id: string;
  requirement_id: string;
  title: string;
  description: string;
  priority: "low" | "medium" | "high" | "critical";
  evidence: AnalysisEvidence[];
  status: "DRAFT" | "TICKET_PENDING_APPROVAL" | "TICKET_CREATED" | "TICKET_REJECTED" | "TICKET_FAILED";
  pending_action_id: string | null;
  ticket_id: string | null;
  created_at: string;
  updated_at: string;
};

export type PublicationDeliverables = {
  version: {
    version_id: string;
    session_id: string;
    version_number: number;
    content_sha256: string;
    prd: PrdDraft;
    published_by: string;
    published_at: string;
  };
  knowledge_candidates: KnowledgeCandidate[];
  action_items: ActionItemDraft[];
};

export function listAnalysisSessions(): Promise<AnalysisSession[]> {
  return agentRequest<AnalysisSession[]>("/analysis/sessions");
}

export function listPublicationQueue(): Promise<AnalysisSession[]> {
  return agentRequest<AnalysisSession[]>("/analysis/publication-queue");
}

export function createAnalysisSession(objective: string, assetIds: string[]): Promise<AnalysisSession> {
  return agentRequest<AnalysisSession>("/analysis/sessions", {
    method: "POST", headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ objective, asset_ids: assetIds }),
  });
}

export function confirmAnalysisSession(
  sessionId: string, resumeToken: string, answers: Record<string, string>,
): Promise<AnalysisSession> {
  return agentRequest<AnalysisSession>(`/analysis/sessions/${sessionId}/confirm`, {
    method: "POST", headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ resume_token: resumeToken, answers }),
  });
}

export function requestPrdPublication(sessionId: string): Promise<AnalysisSession> {
  return agentRequest<AnalysisSession>(`/analysis/sessions/${sessionId}/publication/request`, {
    method: "POST",
  });
}

export function approvePrdPublication(
  sessionId: string, requestId: string, approvalToken: string,
): Promise<AnalysisSession> {
  return agentRequest<AnalysisSession>(`/analysis/sessions/${sessionId}/publication/approve`, {
    method: "POST", headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      request_id: requestId, approval_token: approvalToken, confirmation: "PUBLISH",
    }),
  });
}

export function listAnalysisAudit(sessionId: string): Promise<AnalysisAuditEvent[]> {
  return agentRequest<AnalysisAuditEvent[]>(`/analysis/sessions/${sessionId}/audit`);
}

export function getPublicationDeliverables(sessionId: string): Promise<PublicationDeliverables> {
  return agentRequest<PublicationDeliverables>(`/analysis/sessions/${sessionId}/deliverables`);
}

export function decideKnowledgeCandidate(
  sessionId: string, candidateId: string, approved: boolean,
): Promise<KnowledgeCandidate> {
  return agentRequest<KnowledgeCandidate>(
    `/analysis/sessions/${sessionId}/knowledge-candidates/${candidateId}/decision`,
    {
      method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ approved }),
    },
  );
}

export function createActionTicketDraft(
  sessionId: string, actionItemId: string,
): Promise<{ action_item: ActionItemDraft; pending_action_id: string }> {
  return agentRequest<{ action_item: ActionItemDraft; pending_action_id: string }>(`/analysis/sessions/${sessionId}/action-items/${actionItemId}/ticket-draft`, {
    method: "POST",
  });
}
