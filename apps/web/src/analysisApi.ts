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
  publication_status: "DRAFT";
};
export type AnalysisSession = {
  session_id: string;
  tenant_id: string;
  owner_id: string;
  objective: string;
  asset_ids: string[];
  status: "RUNNING" | "WAITING_CONFIRMATION" | "DRAFT_READY" | "FAILED";
  current_stage: number;
  resume_token: string | null;
  stages: AnalysisStage[];
  open_questions: AnalysisQuestion[];
  confirmations: Record<string, string>;
  prd: PrdDraft | null;
  created_at: string;
  updated_at: string;
};

export function listAnalysisSessions(): Promise<AnalysisSession[]> {
  return agentRequest<AnalysisSession[]>("/analysis/sessions");
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
