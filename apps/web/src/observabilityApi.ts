import type { ActorRole } from "./apiClient";
import { API_BASE_URL, parseJsonResponse, safeFetch } from "./apiClient";
import type { Source, TraceStep } from "./api";


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
  // 阶段 0.8 影子路由：服务端最终模式 / 系统自选模式分布、一致率与不一致配对
  execution_mode_usage?: Record<string, number>;
  shadow_mode_usage?: Record<string, number>;
  mode_agreement_samples?: number;
  mode_agreement_rate?: number;
  mode_disagreements?: Record<string, number>;
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

export async function getMetricsSummary(signal?: AbortSignal): Promise<ChatMetricsSummary> {
  const response = await safeFetch(`${API_BASE_URL}/metrics/summary`, { signal });
  return parseJsonResponse<ChatMetricsSummary>(response);
}

export async function getToolMetrics(signal?: AbortSignal): Promise<ToolMetricsSummary> {
  const response = await safeFetch(`${API_BASE_URL}/metrics/tools`, { signal });
  return parseJsonResponse<ToolMetricsSummary>(response);
}

export async function listToolCalls(limit = 20, actorRole: ActorRole = "operator", signal?: AbortSignal): Promise<ToolCallLog[]> {
  const response = await safeFetch(`${API_BASE_URL}/tool-calls?limit=${limit}`, {
    signal,
    headers: { "X-User-Role": actorRole },
  });
  return parseJsonResponse<ToolCallLog[]>(response);
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

export type ChatLogDetail = ChatLog & { trace: TraceStep[]; sources: Source[] };

export type FeedbackResult = {
  log_id: number;
  feedback: number;
  feedback_note: string;
};

export async function listChatLogs(outcome = "", limit = 50, actorRole: ActorRole = "operator", signal?: AbortSignal): Promise<ChatLog[]> {
  const params = new URLSearchParams({ limit: String(limit) });
  if (outcome) params.set("outcome", outcome);
  const response = await safeFetch(`${API_BASE_URL}/chat-logs?${params.toString()}`, {
    signal,
    headers: { "X-User-Role": actorRole },
  });
  return parseJsonResponse<ChatLog[]>(response);
}

export async function getChatLogDetail(logId: number, actorRole: ActorRole = "operator", signal?: AbortSignal): Promise<ChatLogDetail> {
  const response = await safeFetch(`${API_BASE_URL}/chat-logs/${logId}`, {
    signal,
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
