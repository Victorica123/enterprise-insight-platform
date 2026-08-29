export type WorkspaceSession = {
  userId: string;
  username: string;
  tenantId: string;
  role: "viewer" | "operator" | "admin";
  workspaceType: "personal" | "team";
  token: string;
};

const SESSION_KEY = "enterprise-insight.session.v1";

export function loadSession(): WorkspaceSession | null {
  try {
    const raw = window.localStorage.getItem(SESSION_KEY);
    if (!raw) return null;
    const parsed = JSON.parse(raw) as Partial<WorkspaceSession>;
    return parsed.userId && parsed.username && parsed.tenantId && parsed.role
      && parsed.workspaceType && parsed.token
      ? parsed as WorkspaceSession
      : null;
  } catch {
    return null;
  }
}

export function saveSession(session: WorkspaceSession): void {
  window.localStorage.setItem(SESSION_KEY, JSON.stringify(session));
}

export function clearSession(): void {
  window.localStorage.removeItem(SESSION_KEY);
}

export function accessToken(): string | null {
  return loadSession()?.token ?? null;
}
