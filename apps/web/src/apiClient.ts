import { accessToken } from "./session";

export type ActorRole = "viewer" | "operator" | "admin";

export const API_BASE_URL = import.meta.env.VITE_API_BASE_URL ?? "http://127.0.0.1:8000";

export async function agentRequest<T>(path: string, init?: RequestInit): Promise<T> {
  return parseJsonResponse<T>(await safeFetch(`${API_BASE_URL}${path}`, init));
}

export async function safeFetch(input: RequestInfo | URL, init?: RequestInit): Promise<Response> {
	const headers = new Headers(init?.headers);
	const token = accessToken();
	if (token) headers.set("Authorization", `Bearer ${token}`);
  try {
		return await fetch(input, { ...init, headers });
  } catch (error) {
    if (error instanceof TypeError) {
      throw new Error(
        `无法连接后端服务。请确认 FastAPI 已启动，地址为 ${API_BASE_URL}，并检查端口、CORS 或网络拦截。`,
        { cause: error },
      );
    }

    throw error;
  }
}

export async function parseJsonResponse<T>(response: Response): Promise<T> {
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
