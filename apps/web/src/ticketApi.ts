import type { ActorRole } from "./apiClient";
import { API_BASE_URL, parseJsonResponse, safeFetch } from "./apiClient";


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

// V3: 工单 API

export async function listTickets(status?: string, signal?: AbortSignal): Promise<TicketListResponse> {
  const params = status ? `?status=${status}` : "";
  const response = await safeFetch(`${API_BASE_URL}/tickets${params}`, { signal });
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

export async function listPendingActions(status = "pending", actorRole: ActorRole = "operator", signal?: AbortSignal): Promise<PendingActionResponse[]> {
  const response = await safeFetch(`${API_BASE_URL}/pending-actions?status=${status}`, {
    signal,
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
