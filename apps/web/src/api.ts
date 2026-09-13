import type { ActorRole } from "./apiClient";
import { API_BASE_URL, parseJsonResponse, safeFetch } from "./apiClient";
import type { PendingActionResponse, ToolCallRecord } from "./ticketApi";

export { API_BASE_URL, agentRequest, isPermissionError } from "./apiClient";
export type { ActorRole } from "./apiClient";
export * from "./graphApi";
export * from "./observabilityApi";
export * from "./ticketApi";
export * from "./chatApi";
export * from "./knowledgeApi";

export type AnswerMode = "auto" | "local" | "api";
export type RetrieverMode = "keyword" | "embedding" | "hybrid";
export type WorkflowMode = "standard" | "agentic";

export type DocumentSummary = {
  document_id: string;
  filename: string;
  chunk_count: number;
  created_at: string;
  source_type: "document" | "video" | "knowledge";
  managed: boolean;
};

export type DocumentUploadResponse = {
  document_id: string;
  filename: string;
  chunk_count: number;
};

export type CacheMetric = {
  entries: number;
  max_entries: number;
  hits: number;
  misses: number;
  requests: number;
  hit_rate: number;
};

export type CacheObservability = {
  scope: "process";
  embedding_vectors: CacheMetric;
  chunk_snapshots: CacheMetric;
};

export type EmbeddingCoverageStatus = {
  total_chunks: number;
  embedded_chunks: number;
  missing_chunks: number;
  coverage: number;
  embedded_chunks_v2?: number;
  missing_chunks_v2?: number;
};

export type EmbeddingStatus = EmbeddingCoverageStatus & {
  cache: CacheObservability;
};

export type EmbeddingRebuildResponse = EmbeddingStatus & {
  updated_chunks: number;
};

export type SystemStatus = {
  status: string;
  document_count: number;
  chunk_count: number;
  llm_provider: string;
  llm_configured: boolean;
  default_answer_mode: AnswerMode;
  default_retriever_mode: RetrieverMode;
  embedding: EmbeddingCoverageStatus;
};

export type Source = {
  source_type: "document" | "video";
  origin_type: "uploaded_document" | "media_transcript" | "approved_knowledge";
  document_id: string;
  filename: string;
  chunk_index: number;
  chunk_indices?: number[];
  parent_key?: string;
  score: number;
  content: string;
  title?: string;
	asset_id?: string | null;
	segment_id?: string | null;
	start_ms?: number | null;
	end_ms?: number | null;
	speaker?: string | null;
  knowledge_candidate_id?: string | null;
  prd_version_id?: string | null;
  content_sha256?: string | null;
  knowledge_version_id?: string | null;
  knowledge_version_number?: number | null;
  knowledge_lifecycle_status?: "ACTIVE" | "SUPERSEDED" | "REVOKED" | null;
  superseded_by_document_id?: string | null;
};

export type ChatResponse = {
  answer: string;
  sources: Source[];
  trace: TraceStep[];
  agent_summary: AgentSummary | null;
  pending_actions: PendingActionResponse[];
  token_usage: TokenUsage | null;
  log_id: number;
  conversation_id?: string | null;
  exchange_id?: string | null;
  follow_up?: string[];
};

export type TokenUsage = {
  prompt_tokens: number;
  completion_tokens: number;
  total_tokens: number;
  estimated_cost_usd: number;
  source: string;
};

export type AgentSummary = {
  workflow: string;
  intent: string;
  complexity: string;
  retrieval_rounds: number;
  queries: string[];
  evidence_status: string;
  citation_status: string;
  agents: string[];
  tool_calls: ToolCallRecord[];
  pending_approval: boolean;
  graph_entities: string[];
  graph_paths: string[];
  execution_mode?: string;
  clarify_question?: string | null;
};

export type TraceStep = {
  name: string;
  status: string;
  detail: string;
  duration_ms?: number | null;
};

export async function askQuestion(
  question: string,
  answerMode: AnswerMode,
  retrieverMode: RetrieverMode,
  workflowMode: WorkflowMode,
  actorRole: ActorRole = "operator",
  actorUser = "anonymous",
	assetIds: string[] = [],
): Promise<ChatResponse> {
  const response = await safeFetch(`${API_BASE_URL}/chat`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      "X-User-Role": actorRole,
      "X-User-Id": actorUser,
    },
    body: JSON.stringify({
      question,
      answer_mode: answerMode,
      retriever_mode: retrieverMode,
      workflow_mode: workflowMode,
			asset_ids: assetIds,
    }),
  });

  const payload = await parseJsonResponse<ChatResponse>(response);
  return {
    ...payload,
    trace: payload.trace ?? [],
    agent_summary: payload.agent_summary ?? null,
    pending_actions: payload.pending_actions ?? [],
    token_usage: payload.token_usage ?? null,
    log_id: payload.log_id ?? 0,
  };
}
