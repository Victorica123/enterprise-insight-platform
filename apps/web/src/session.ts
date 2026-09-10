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

/** Client-side scheduling hint only; API services still verify signature and expiry. */
export function tokenExpiresAt(token: string): number | null {
  try {
    const payload = token.split(".")[1];
    if (!payload) return null;
    const normalized = payload.replace(/-/g, "+").replace(/_/g, "/");
    const padded = normalized.padEnd(Math.ceil(normalized.length / 4) * 4, "=");
    const decoded = JSON.parse(atob(padded)) as { exp?: number };
    return typeof decoded.exp === "number" ? decoded.exp * 1000 : null;
  } catch {
    return null;
  }
}
