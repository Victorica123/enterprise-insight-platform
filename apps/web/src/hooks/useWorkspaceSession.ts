import * as React from "react";
import { logout } from "../mediaApi";
import { clearOidcSession, oidcRefreshAvailable, refreshOidcLogin } from "../oidc";
import { clearSession, loadSession, saveSession, tokenExpiresAt, type WorkspaceSession } from "../session";

export function useWorkspaceSession() {
  const [session, setSession] = React.useState<WorkspaceSession | null>(loadSession);
  const [error, setError] = React.useState<string | null>(null);
  const acceptSession = React.useCallback((next: WorkspaceSession) => {
    saveSession(next);
    setSession(next);
    setError(null);
  }, []);
  React.useEffect(() => {
    const sync = () => setSession(loadSession());
    window.addEventListener("storage", sync);
    return () => window.removeEventListener("storage", sync);
  }, []);
  React.useEffect(() => {
    if (!session) return;
    const expiresAt = tokenExpiresAt(session.token);
    if (expiresAt === null) return;
    const canRefresh = oidcRefreshAvailable();
    let active = true;
    let pending = false;
    let timer: number;
    const checkExpiry = () => {
      if (!active || pending || loadSession()?.token !== session.token) return;
      window.clearTimeout(timer);
      const delay = expiresAt - Date.now() - (canRefresh ? 60_000 : 0);
      if (delay > 0) { timer = window.setTimeout(checkExpiry, Math.min(delay, 2_147_483_647)); return; }
      pending = true;
      if (canRefresh) {
        void refreshOidcLogin(session.tenantId).then((next) => {
          if (active && loadSession()?.token === session.token) acceptSession(next);
        }).catch(() => {
          if (!active || loadSession()?.token !== session.token) return;
          clearOidcSession(); clearSession(); setSession(null);
          setError("统一身份会话已过期，请重新登录。");
        });
      } else {
        clearSession(); setSession(null); setError("登录已过期，请重新登录。");
      }
    };
    checkExpiry();
    window.addEventListener("focus", checkExpiry);
    document.addEventListener("visibilitychange", checkExpiry);
    return () => {
      active = false; window.clearTimeout(timer);
      window.removeEventListener("focus", checkExpiry);
      document.removeEventListener("visibilitychange", checkExpiry);
    };
  }, [session, acceptSession]);
  const endSession = async () => {
    const revocation = logout();
    clearOidcSession(); clearSession(); setSession(null);
    try { await revocation; } catch { /* Local credentials are already cleared. */ }
  };
  return { session, error, acceptSession, endSession };
}
