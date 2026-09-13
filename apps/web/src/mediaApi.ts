import { accessToken, type WorkspaceSession } from "./session";

export const MEDIA_API_BASE_URL = import.meta.env.VITE_MEDIA_API_BASE_URL ?? "http://127.0.0.1:8081";

type MediaEnvelope<T> = { success: boolean; data: T; message?: string };

export type WorkspaceRole = "OWNER" | "ADMIN" | "MEMBER" | "VIEWER";

export type WorkspaceSummary = {
  tenantId: string;
  name: string;
  workspaceType: "personal" | "team";
  role: WorkspaceRole;
  jwtRole: WorkspaceSession["role"];
  createdBy: string;
  createdAt: string;
  joinedAt: string;
};

export type WorkspaceMember = {
  userId: string;
  username: string;
  role: WorkspaceRole;
  jwtRole: WorkspaceSession["role"];
  joinedAt: string;
};

export type WorkspaceInvitation = {
  invitationCode: string;
  tenantId: string;
  workspaceName: string;
  expiresAt: string;
};

export type TranscriptSegment = {
  segmentId: string;
  sequence: number;
  startMs: number;
  endMs: number;
  speaker: string | null;
  text: string;
};

export type MediaTask = {
  taskId: string;
  videoId: string;
  tenantId: string;
  owner: string;
  fileName: string;
  transcript: string | null;
  transcriptSegments: TranscriptSegment[];
  transcriptLanguage: string | null;
  transcriptDurationMs: number | null;
  transcriptVersion: number;
  mediaRetained: boolean;
  transcriptRetained: boolean;
  summary: string | null;
  status: "QUEUED" | "TRANSCRIBING" | "SUMMARIZING" | "COMPLETED" | "FAILED";
  errorMessage: string | null;
  createdAt: string;
  updatedAt: string;
};

export type MediaRuntime = {
  dispatchMode: "local-async" | "rocketmq";
  mqEnabled: boolean;
  transcriptMode: "mock" | "whisper-api";
  summaryMode: "mock" | "llm-api";
  mockDelayMs: number;
  maxActiveTasksPerUser: number;
  mqConsumerThreads: number;
  storageType: string;
  jwtAlgorithm: string;
  oidcEnabled: boolean;
  modelEgressAllowed: boolean;
  retentionEnabled: boolean;
  mediaRetentionDays: number;
  transcriptRetentionDays: number;
  auditRetentionDays: number;
};

export type MediaTaskStage = {
  id: number;
  runId: string;
  stage: "STORAGE_RESOLVE" | "AUDIO_EXTRACTION" | "TRANSCRIPTION" | "SUMMARY" | "RESULT_REUSE" | "RESULT_COMMIT" | "DELIVERY";
  status: "RUNNING" | "SUCCEEDED" | "FAILED" | "ABANDONED";
  startedAt: string;
  finishedAt: string | null;
  durationMs: number | null;
  errorCode: "STAGE_FAILED" | "LEASE_RECOVERED" | "DELIVERY_REJECTED" | "DELIVERY_RETRY" | "LEASE_LOST" | null;
};
export type MediaTaskStagePage = { items: MediaTaskStage[]; nextCursor: number; hasMore: boolean };

export function listMediaTaskStages(taskId: string, after = 0, signal?: AbortSignal): Promise<MediaTaskStagePage> {
  return mediaRequest(`/api/workflow/tasks/${encodeURIComponent(taskId)}/stages?after=${after}&limit=50`, { signal });
}

export async function authenticate(
  mode: "login" | "register",
  username: string,
  password: string,
): Promise<WorkspaceSession> {
  return mediaRequest<WorkspaceSession>(`/api/auth/${mode}`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ username, password }),
  }, false);
}

export async function exchangeOidcToken(
  externalAccessToken: string,
  workspaceId?: string,
): Promise<WorkspaceSession> {
  const headers = new Headers({ Authorization: `Bearer ${externalAccessToken}` });
  if (workspaceId) headers.set("X-Workspace-Id", workspaceId);
  return mediaRequest<WorkspaceSession>("/api/auth/oidc/exchange", {
    method: "POST",
    headers,
  }, false);
}

export async function logout(): Promise<void> {
  await mediaRequest<void>("/api/auth/logout", { method: "POST" });
}

export async function listWorkspaces(signal?: AbortSignal): Promise<WorkspaceSummary[]> {
  return mediaRequest<WorkspaceSummary[]>("/api/workspaces", { signal });
}

export async function createWorkspace(name: string): Promise<WorkspaceSummary> {
  return mediaRequest<WorkspaceSummary>("/api/workspaces", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ name }),
  });
}

export async function acceptWorkspaceInvitation(invitationCode: string): Promise<WorkspaceSummary> {
  return mediaRequest<WorkspaceSummary>("/api/workspaces/invitations/accept", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ invitationCode }),
  });
}

export async function switchWorkspace(tenantId: string): Promise<WorkspaceSession> {
  return mediaRequest<WorkspaceSession>(`/api/workspaces/${tenantId}/switch`, { method: "POST" });
}

export async function listWorkspaceMembers(tenantId: string, signal?: AbortSignal): Promise<WorkspaceMember[]> {
  return mediaRequest<WorkspaceMember[]>(`/api/workspaces/${tenantId}/members`, { signal });
}

export async function createWorkspaceInvitation(tenantId: string): Promise<WorkspaceInvitation> {
  return mediaRequest<WorkspaceInvitation>(`/api/workspaces/${tenantId}/invitations`, { method: "POST" });
}

export async function updateWorkspaceMemberRole(
  tenantId: string,
  userId: string,
  role: Exclude<WorkspaceRole, "OWNER">,
): Promise<WorkspaceMember> {
  return mediaRequest<WorkspaceMember>(`/api/workspaces/${tenantId}/members/${userId}`, {
    method: "PATCH",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ role }),
  });
}

export async function listMediaTasks(signal?: AbortSignal): Promise<MediaTask[]> {
  return mediaRequest<MediaTask[]>("/api/workflow/tasks", { signal });
}

export async function getMediaRuntime(signal?: AbortSignal): Promise<MediaRuntime> {
  return mediaRequest<MediaRuntime>("/api/workflow/runtime", { signal });
}

export async function uploadVideo(file: File): Promise<{ taskId: string; videoId: string; status: string }> {
  const body = new FormData();
  body.append("file", file);
  return mediaRequest("/api/media/upload/file", { method: "POST", body });
}

export async function retryMediaTask(taskId: string): Promise<MediaTask> {
  return mediaRequest<MediaTask>(`/api/workflow/tasks/${taskId}/retry`, { method: "POST" });
}

export async function deleteMediaTask(taskId: string): Promise<void> {
  await mediaRequest(`/api/workflow/tasks/${taskId}`, { method: "DELETE" });
}

export async function createPlayback(taskId: string, signal?: AbortSignal): Promise<{ url: string; expiresInSeconds: number }> {
  const result = await mediaRequest<{ token: string; streamUrl: string; expiresInSeconds: number }>(
    `/api/media/video/${taskId}/playback-token`, { signal },
  );
  return {
    url: new URL(result.streamUrl, MEDIA_API_BASE_URL).toString(),
    expiresInSeconds: result.expiresInSeconds,
  };
}

async function mediaRequest<T>(path: string, init: RequestInit = {}, requireAuth = true): Promise<T> {
  const headers = new Headers(init.headers);
  const token = accessToken();
  if (requireAuth && token) headers.set("Authorization", `Bearer ${token}`);
  let response: Response;
  try {
    response = await fetch(`${MEDIA_API_BASE_URL}${path}`, { ...init, headers });
  } catch (error) {
    if (init.signal?.aborted || (error instanceof Error && error.name === "AbortError")) throw error;
    throw new Error(`无法连接本地 Media Service（${MEDIA_API_BASE_URL}）。无需域名，但请先启动本机服务。`, { cause: error });
  }
  const payload = await response.json().catch(() => null) as MediaEnvelope<T> | null;
  if (!response.ok || !payload?.success) {
    const message = payload?.message || `Media Service 请求失败（${response.status}）`;
    const error = new Error(message) as Error & { status?: number };
    error.status = response.status;
    throw error;
  }
  return payload.data;
}
