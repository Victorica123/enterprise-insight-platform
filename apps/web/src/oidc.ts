import { exchangeOidcToken } from "./mediaApi";
import type { WorkspaceSession } from "./session";

const OIDC_ISSUER = (import.meta.env.VITE_OIDC_ISSUER ?? "").replace(/\/$/, "");
const OIDC_CLIENT_ID = import.meta.env.VITE_OIDC_CLIENT_ID ?? "enterprise-insight-web";
const VERIFIER_KEY = "enterprise-insight.oidc.verifier";
const STATE_KEY = "enterprise-insight.oidc.state";
const REFRESH_TOKEN_KEY = "enterprise-insight.oidc.refresh-token";
let sessionGeneration = 0;
let pendingRefresh: Promise<OidcTokenResponse> | null = null;

export function oidcEnabled(): boolean {
  return import.meta.env.VITE_OIDC_ENABLED === "true" && Boolean(OIDC_ISSUER);
}

export async function beginOidcLogin(): Promise<void> {
  if (!oidcEnabled()) throw new Error("OIDC 登录未配置");
  clearOidcSession();
  const verifier = randomUrlSafe(64);
  const state = randomUrlSafe(32);
  sessionStorage.setItem(VERIFIER_KEY, verifier);
  sessionStorage.setItem(STATE_KEY, state);
  const challenge = base64Url(await crypto.subtle.digest("SHA-256", new TextEncoder().encode(verifier)));
  const url = new URL(`${OIDC_ISSUER}/protocol/openid-connect/auth`);
  url.searchParams.set("client_id", OIDC_CLIENT_ID);
  url.searchParams.set("redirect_uri", redirectUri());
  url.searchParams.set("response_type", "code");
  url.searchParams.set("scope", "openid profile email");
  url.searchParams.set("state", state);
  url.searchParams.set("code_challenge", challenge);
  url.searchParams.set("code_challenge_method", "S256");
  window.location.assign(url.toString());
}

export async function finishOidcLogin(): Promise<WorkspaceSession | null> {
  const generation = sessionGeneration;
  const query = new URLSearchParams(window.location.search);
  const code = query.get("code");
  const returnedState = query.get("state");
  const providerError = query.get("error_description") || query.get("error");
  if (!code && !providerError) return null;
  try {
    if (providerError) throw new Error(`身份服务拒绝登录：${providerError}`);
    if (!code) throw new Error("OIDC 回调缺少授权码");
    const verifier = sessionStorage.getItem(VERIFIER_KEY);
    const expectedState = sessionStorage.getItem(STATE_KEY);
    if (!verifier || !expectedState || returnedState !== expectedState) {
      throw new Error("OIDC 登录状态校验失败，请重新登录");
    }
    const response = await fetch(`${OIDC_ISSUER}/protocol/openid-connect/token`, {
      method: "POST",
      headers: { "Content-Type": "application/x-www-form-urlencoded" },
      body: new URLSearchParams({
        grant_type: "authorization_code",
        client_id: OIDC_CLIENT_ID,
        redirect_uri: redirectUri(),
        code,
        code_verifier: verifier,
      }),
    });
    const payload = await response.json().catch(() => null) as OidcTokenResponse | null;
    if (!response.ok || !payload?.access_token) {
      throw new Error(payload?.error_description || `OIDC code exchange failed (${response.status})`);
    }
    requireCurrentSession(generation);
    const session = await exchangeOidcToken(payload.access_token);
    requireCurrentSession(generation);
    sessionStorage.removeItem(REFRESH_TOKEN_KEY);
    rememberRefreshToken(payload.refresh_token);
    return session;
  } finally {
    sessionStorage.removeItem(VERIFIER_KEY);
    sessionStorage.removeItem(STATE_KEY);
    window.history.replaceState({}, document.title, `${window.location.pathname}${window.location.hash}`);
  }
}

export function oidcRefreshAvailable(): boolean {
  return oidcEnabled() && Boolean(sessionStorage.getItem(REFRESH_TOKEN_KEY));
}

export async function refreshOidcLogin(workspaceId: string): Promise<WorkspaceSession> {
  const generation = sessionGeneration;
  if (!pendingRefresh) {
    const request = refreshProviderToken(generation);
    pendingRefresh = request;
    void request.finally(() => {
      if (pendingRefresh === request) pendingRefresh = null;
    }).catch(() => { /* the caller handles the original rejection */ });
  }
  const payload = await pendingRefresh;
  requireCurrentSession(generation);
  let session: WorkspaceSession;
  try {
    session = await exchangeOidcToken(payload.access_token!, workspaceId);
  } catch (error) {
    requireCurrentSession(generation);
    // Media hides absent membership behind 404; outages and invalid identity
    // must never silently change the active workspace.
    if ((error as { status?: number } | null)?.status !== 404) throw error;
    session = await exchangeOidcToken(payload.access_token!);
  }
  requireCurrentSession(generation);
  return session;
}

async function refreshProviderToken(generation: number): Promise<OidcTokenResponse> {
  const refreshToken = sessionStorage.getItem(REFRESH_TOKEN_KEY);
  if (!oidcEnabled() || !refreshToken) throw new Error("OIDC 会话不可续期");
  const response = await fetch(`${OIDC_ISSUER}/protocol/openid-connect/token`, {
    method: "POST",
    headers: { "Content-Type": "application/x-www-form-urlencoded" },
    body: new URLSearchParams({
      grant_type: "refresh_token",
      client_id: OIDC_CLIENT_ID,
      refresh_token: refreshToken,
    }),
  });
  const payload = await response.json().catch(() => null) as OidcTokenResponse | null;
  requireCurrentSession(generation);
  if (!response.ok || !payload?.access_token) {
    clearOidcSession();
    throw new Error(payload?.error_description || `OIDC session refresh failed (${response.status})`);
  }
  rememberRefreshToken(payload.refresh_token);
  return payload;
}

export function clearOidcSession(): void {
  sessionGeneration += 1;
  pendingRefresh = null;
  sessionStorage.removeItem(VERIFIER_KEY);
  sessionStorage.removeItem(STATE_KEY);
  sessionStorage.removeItem(REFRESH_TOKEN_KEY);
}

function requireCurrentSession(generation: number): void {
  if (generation !== sessionGeneration) throw new Error("OIDC 会话已结束");
}

type OidcTokenResponse = {
  access_token?: string;
  refresh_token?: string;
  error_description?: string;
};

function rememberRefreshToken(value?: string): void {
  if (value) sessionStorage.setItem(REFRESH_TOKEN_KEY, value);
}

function redirectUri(): string {
  return `${window.location.origin}${window.location.pathname}`;
}

function randomUrlSafe(length: number): string {
  const bytes = crypto.getRandomValues(new Uint8Array(length));
  return base64Url(bytes);
}

function base64Url(value: ArrayBuffer | Uint8Array): string {
  const bytes = value instanceof Uint8Array ? value : new Uint8Array(value);
  let binary = "";
  bytes.forEach((byte) => { binary += String.fromCharCode(byte); });
  return btoa(binary).replace(/\+/g, "-").replace(/\//g, "_").replace(/=+$/, "");
}
