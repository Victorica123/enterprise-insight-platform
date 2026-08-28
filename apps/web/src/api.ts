export type AnswerMode = "auto" | "local" | "api";
export type RetrieverMode = "keyword" | "embedding" | "hybrid";
export type WorkflowMode = "standard" | "agentic";
export type ActorRole = "viewer" | "operator" | "admin";

export type DocumentSummary = {
  document_id: string;
  filename: string;
  chunk_count: number;
  created_at: string;
};

export type DocumentUploadResponse = {
  document_id: string;
  filename: string;
  chunk_count: number;
};

export type EmbeddingStatus = {
  total_chunks: number;
  embedded_chunks: number;
  missing_chunks: number;
  coverage: number;
  embedded_chunks_v2?: number;
  missing_chunks_v2?: number;
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
  embedding: EmbeddingStatus;
};

export type Source = {
  document_id: string;
  filename: string;
  chunk_index: number;
  score: number;
  content: string;
  title?: string;
};

export type ToolCallRecord = {
  tool_name: string;
  success: boolean;
  result_summary: string;
  pending_action_id: string;
  status: string;
  duration_ms: number;
};

export type PendingActionResponse = {
  action_id: string;
  action_type: string;
  payload: Record<string, unknown>;
  status: string;
  requested_by: string;
  resolved_by: string;
  result: Record<string, unknown>;
  error_message: string;
  duration_ms: number;
  execution_count: number;
  created_at: string;
  expires_at: string;
  resolved_at: string;
};

export type ChatResponse = {
  answer: string;
  sources: Source[];
  trace: TraceStep[];
  agent_summary: AgentSummary | null;
  pending_actions: PendingActionResponse[];
  token_usage: TokenUsage | null;
  log_id: number;
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
};

export type ChatMetricsSummary = {
  total_requests: number;
  answered_requests: number;
  refused_requests: number;
  error_requests: number;
  answer_rate: number;
  refusal_rate: number;
  error_rate: number;
  evidence_pass_rate: number;
  citation_ready_rate: number;
  avg_latency_ms: number;
  p95_latency_ms: number;
  avg_retrieval_rounds: number;
  avg_query_count: number;
  avg_source_count: number;
  workflow_usage: Record<string, number>;
  answer_mode_usage: Record<string, number>;
  retriever_usage: Record<string, number>;
  intent_usage: Record<string, number>;
  avg_latency_by_workflow: Record<string, number>;
  avg_latency_by_answer_mode: Record<string, number>;
  total_prompt_tokens: number;
  total_completion_tokens: number;
  total_tokens: number;
  avg_tokens_per_request: number;
  total_estimated_cost_usd: number;
  avg_cost_per_request_usd: number;
  tokens_by_answer_mode: Record<string, number>;
  cost_by_answer_mode: Record<string, number>;
  feedback_count: number;
  positive_feedback: number;
  negative_feedback: number;
  satisfaction_rate: number;
};

export type TraceStep = {
  name: string;
  status: string;
  detail: string;
};

// V3 types
export type TicketResponse = {
  ticket_id: string;
  title: string;
  description: string;
  status: string;
  priority: string;
  assignee: string;
  source_document_ids: string[];
  risk_level: string;
  created_at: string;
  updated_at: string;
};

export type TicketListResponse = {
  tickets: TicketResponse[];
  total: number;
  summary: Record<string, unknown>;
};

export type ApprovalResponse = {
  action_id: string;
  status: string;
  result: Record<string, unknown>;
  message: string;
  already_resolved: boolean;
};

export type ToolMetricsSummary = {
  total_calls: number;
  succeeded_calls: number;
  pending_calls: number;
  failed_calls: number;
  rejected_calls: number;
  expired_calls: number;
  success_rate: number;
  approval_rate: number;
  avg_duration_ms: number;
  p95_duration_ms: number;
  exact_once_violations: number;
  by_tool: Record<string, number>;
  by_status: Record<string, number>;
};

export type ToolCallLog = {
  call_id: string;
  tool_name: string;
  action_id: string;
  operation: string;
  requires_approval: boolean;
  status: string;
  actor_role: string;
  input: Record<string, unknown>;
  result: Record<string, unknown>;
  error_message: string;
  duration_ms: number;
  created_at: string;
};

const API_BASE_URL = import.meta.env.VITE_API_BASE_URL ?? "http://127.0.0.1:8000";

export async function listDocuments(): Promise<DocumentSummary[]> {
  const response = await safeFetch(`${API_BASE_URL}/documents`);
  return parseJsonResponse<DocumentSummary[]>(response);
}

export async function getSystemStatus(): Promise<SystemStatus> {
  const response = await safeFetch(`${API_BASE_URL}/system/status`);
  return parseJsonResponse<SystemStatus>(response);
}

export async function getMetricsSummary(): Promise<ChatMetricsSummary> {
  const response = await safeFetch(`${API_BASE_URL}/metrics/summary`);
  return parseJsonResponse<ChatMetricsSummary>(response);
}

export async function getToolMetrics(): Promise<ToolMetricsSummary> {
  const response = await safeFetch(`${API_BASE_URL}/metrics/tools`);
  return parseJsonResponse<ToolMetricsSummary>(response);
}

export async function listToolCalls(limit = 20, actorRole: ActorRole = "operator"): Promise<ToolCallLog[]> {
  const response = await safeFetch(`${API_BASE_URL}/tool-calls?limit=${limit}`, {
    headers: { "X-User-Role": actorRole },
  });
  return parseJsonResponse<ToolCallLog[]>(response);
}

export async function uploadDocument(file: File, actorRole: ActorRole = "operator"): Promise<DocumentUploadResponse> {
  const formData = new FormData();
  formData.append("file", file);

  const response = await safeFetch(`${API_BASE_URL}/documents`, {
    method: "POST",
    headers: { "X-User-Role": actorRole },
    body: formData,
  });
  return parseJsonResponse<DocumentUploadResponse>(response);
}

export async function deleteDocument(documentId: string, actorRole: ActorRole = "operator"): Promise<void> {
  const response = await safeFetch(`${API_BASE_URL}/documents/${documentId}`, {
    method: "DELETE",
    headers: { "X-User-Role": actorRole },
  });
  await parseJsonResponse(response);
}

export async function getEmbeddingStatus(): Promise<EmbeddingStatus> {
  const response = await safeFetch(`${API_BASE_URL}/embeddings/status`);
  return parseJsonResponse<EmbeddingStatus>(response);
}

export async function rebuildEmbeddings(actorRole: ActorRole = "operator"): Promise<EmbeddingRebuildResponse> {
  const response = await safeFetch(`${API_BASE_URL}/embeddings/rebuild`, {
    method: "POST",
    headers: { "X-User-Role": actorRole },
  });
  return parseJsonResponse<EmbeddingRebuildResponse>(response);
}

export async function askQuestion(
  question: string,
  answerMode: AnswerMode,
  retrieverMode: RetrieverMode,
  workflowMode: WorkflowMode,
  actorRole: ActorRole = "operator",
  actorUser = "anonymous",
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

// V3: 工单 API

export async function listTickets(status?: string): Promise<TicketListResponse> {
  const params = status ? `?status=${status}` : "";
  const response = await safeFetch(`${API_BASE_URL}/tickets${params}`);
  return parseJsonResponse<TicketListResponse>(response);
}

export async function getTicket(ticketId: string): Promise<TicketResponse> {
  const response = await safeFetch(`${API_BASE_URL}/tickets/${ticketId}`);
  return parseJsonResponse<TicketResponse>(response);
}

export async function createTicketManual(
  title: string,
  description: string,
  priority: string,
  assignee: string,
  riskLevel: string,
  actorRole: ActorRole = "operator",
): Promise<TicketResponse> {
  const response = await safeFetch(`${API_BASE_URL}/tickets`, {
    method: "POST",
    headers: { "Content-Type": "application/json", "X-User-Role": actorRole },
    body: JSON.stringify({ title, description, priority, assignee, risk_level: riskLevel }),
  });
  return parseJsonResponse<TicketResponse>(response);
}

export async function deleteTicket(ticketId: string, actorRole: ActorRole = "operator"): Promise<void> {
  const response = await safeFetch(`${API_BASE_URL}/tickets/${ticketId}`, {
    method: "DELETE",
    headers: { "X-User-Role": actorRole },
  });
  await parseJsonResponse(response);
}

// V3: 审批 API

export async function listPendingActions(status = "pending", actorRole: ActorRole = "operator"): Promise<PendingActionResponse[]> {
  const response = await safeFetch(`${API_BASE_URL}/pending-actions?status=${status}`, {
    headers: { "X-User-Role": actorRole },
  });
  return parseJsonResponse<PendingActionResponse[]>(response);
}

export async function createStatusDraft(
  ticketId: string,
  newStatus: string,
  actorRole: ActorRole = "operator",
  actorUser = "anonymous",
): Promise<PendingActionResponse> {
  const response = await safeFetch(`${API_BASE_URL}/tickets/${ticketId}/status-draft`, {
    method: "POST",
    headers: { "Content-Type": "application/json", "X-User-Role": actorRole, "X-User-Id": actorUser },
    body: JSON.stringify({ new_status: newStatus }),
  });
  return parseJsonResponse<PendingActionResponse>(response);
}

export async function approveAction(
  actionId: string,
  approved: boolean,
  actorRole: ActorRole = "operator",
  actorUser = "anonymous",
): Promise<ApprovalResponse> {
  const response = await safeFetch(`${API_BASE_URL}/pending-actions/${actionId}/approve`, {
    method: "POST",
    headers: { "Content-Type": "application/json", "X-User-Role": actorRole, "X-User-Id": actorUser },
    body: JSON.stringify({ approved }),
  });
  return parseJsonResponse<ApprovalResponse>(response);
}

// V4: 关系图谱 API

export type GraphEntity = {
  name: string;
  entity_type: string;
  type_label: string;
  mention_count: number;
  document_ids: string[];
};

export type GraphRelation = {
  source_name: string;
  source_type: string;
  relation_type: string;
  target_name: string;
  target_type: string;
  evidence: string;
  document_id: string;
  filename: string;
  chunk_index: number;
};

export type GraphOverview = {
  entity_count: number;
  relation_count: number;
  document_count: number;
  entity_types: Record<string, number>;
  relation_types: Record<string, number>;
  built_at: string;
};

export type GraphRebuildResponse = GraphOverview & { duration_ms: number };

export type GraphPathStep = {
  source: string;
  relation: string;
  target: string;
  forward: boolean;
  display: string;
};

export type GraphPath = {
  steps: GraphPathStep[];
  display: string;
};

export type GraphPathQuery = {
  source: string;
  target: string;
  max_depth: number;
  paths: GraphPath[];
};

export async function getGraphOverview(): Promise<GraphOverview> {
  const response = await safeFetch(`${API_BASE_URL}/graph/overview`);
  return parseJsonResponse<GraphOverview>(response);
}

export async function listGraphEntities(entityType = "", keyword = ""): Promise<GraphEntity[]> {
  const params = new URLSearchParams();
  if (entityType) params.set("entity_type", entityType);
  if (keyword) params.set("keyword", keyword);
  const query = params.toString();
  const response = await safeFetch(`${API_BASE_URL}/graph/entities${query ? `?${query}` : ""}`);
  return parseJsonResponse<GraphEntity[]>(response);
}

export async function listGraphRelations(entity = ""): Promise<GraphRelation[]> {
  const params = entity ? `?entity=${encodeURIComponent(entity)}` : "";
  const response = await safeFetch(`${API_BASE_URL}/graph/relations${params}`);
  return parseJsonResponse<GraphRelation[]>(response);
}

export async function queryGraphPaths(source: string, target: string, maxDepth = 3): Promise<GraphPathQuery> {
  const params = new URLSearchParams({ source, target, max_depth: String(maxDepth) });
  const response = await safeFetch(`${API_BASE_URL}/graph/paths?${params.toString()}`);
  return parseJsonResponse<GraphPathQuery>(response);
}

export async function rebuildGraph(actorRole: ActorRole = "operator"): Promise<GraphRebuildResponse> {
  const response = await safeFetch(`${API_BASE_URL}/graph/rebuild`, {
    method: "POST",
    headers: { "X-User-Role": actorRole },
  });
  return parseJsonResponse<GraphRebuildResponse>(response);
}

// V5: 请求日志与反馈 API

export type ChatLog = {
  log_id: number;
  question: string;
  workflow_mode: string;
  answer_mode: string;
  retriever_mode: string;
  intent: string;
  outcome: string;
  evidence_status: string;
  citation_status: string;
  source_count: number;
  latency_ms: number;
  total_tokens: number;
  estimated_cost_usd: number;
  answer_preview: string;
  feedback: number;
  feedback_note: string;
  created_at: string;
};

export type ChatLogDetail = ChatLog & { trace: TraceStep[] };

export type FeedbackResult = {
  log_id: number;
  feedback: number;
  feedback_note: string;
};

export async function listChatLogs(outcome = "", limit = 50, actorRole: ActorRole = "operator"): Promise<ChatLog[]> {
  const params = new URLSearchParams({ limit: String(limit) });
  if (outcome) params.set("outcome", outcome);
  const response = await safeFetch(`${API_BASE_URL}/chat-logs?${params.toString()}`, {
    headers: { "X-User-Role": actorRole },
  });
  return parseJsonResponse<ChatLog[]>(response);
}

export async function getChatLogDetail(logId: number, actorRole: ActorRole = "operator"): Promise<ChatLogDetail> {
  const response = await safeFetch(`${API_BASE_URL}/chat-logs/${logId}`, {
    headers: { "X-User-Role": actorRole },
  });
  return parseJsonResponse<ChatLogDetail>(response);
}

export async function submitFeedback(
  logId: number,
  rating: "up" | "down",
  note = "",
): Promise<FeedbackResult> {
  const response = await safeFetch(`${API_BASE_URL}/chat-logs/${logId}/feedback`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ rating, note }),
  });
  return parseJsonResponse<FeedbackResult>(response);
}

async function safeFetch(input: RequestInfo | URL, init?: RequestInit): Promise<Response> {
  try {
    return await fetch(input, init);
  } catch (error) {
    if (error instanceof TypeError) {
      throw new Error(
        `无法连接后端服务。请确认 FastAPI 已启动，地址为 ${API_BASE_URL}，并检查端口、CORS 或网络拦截。`,
      );
    }

    throw error;
  }
}

async function parseJsonResponse<T>(response: Response): Promise<T> {
  const payload = await response.json().catch(() => null);

  if (!response.ok) {
    const message = payload?.detail ?? `请求失败，状态码 ${response.status}`;
    const error = new Error(typeof message === "string" ? message : JSON.stringify(message));
    // 附带状态码，调用方可按 403 等给出针对性提示
    (error as Error & { status?: number }).status = response.status;
    throw error;
  }

  return payload as T;
}

/** 判断是否为权限不足（403），用于角色切换提示 */
export function isPermissionError(error: unknown): boolean {
  return typeof error === "object" && error !== null && (error as { status?: number }).status === 403;
}
