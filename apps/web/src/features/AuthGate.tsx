import React from "react";
import { BrainCircuit, KeyRound, Loader2, ShieldCheck } from "lucide-react";
import { authenticate } from "../mediaApi";
import { beginOidcLogin, finishOidcLogin, oidcEnabled } from "../oidc";
import type { WorkspaceSession } from "../session";
import { getErrorMessage } from "./common";
import "../styles/media.css";

export function AuthGate({ onAuthenticated }: { onAuthenticated: (session: WorkspaceSession) => void }) {
  const [mode, setMode] = React.useState<"login" | "register">("login");
  const [username, setUsername] = React.useState("");
  const [password, setPassword] = React.useState("");
  const [busy, setBusy] = React.useState(false);
  const [error, setError] = React.useState<string | null>(null);
  const callbackStarted = React.useRef(false);
  const externalLoginEnabled = oidcEnabled();
  const localLoginEnabled = import.meta.env.VITE_LOCAL_AUTH_ENABLED !== "false";

  React.useEffect(() => {
    if (callbackStarted.current || !externalLoginEnabled) return;
    callbackStarted.current = true;
    if (!new URLSearchParams(window.location.search).has("code")
      && !new URLSearchParams(window.location.search).has("error")) return;
    setBusy(true);
    finishOidcLogin()
      .then((session) => { if (session) onAuthenticated(session); })
      .catch((caught) => setError(getErrorMessage(caught)))
      .finally(() => setBusy(false));
  }, [externalLoginEnabled, onAuthenticated]);

  async function submit(event: React.FormEvent) {
    event.preventDefault();
    setBusy(true);
    setError(null);
    try {
      onAuthenticated(await authenticate(mode, username.trim(), password));
    } catch (caught) {
      setError(getErrorMessage(caught));
    } finally {
      setBusy(false);
    }
  }

  return (
    <main className="auth-shell">
      <section className="auth-card">
        <div className="auth-brand"><BrainCircuit size={30} /><span>Enterprise Insight</span></div>
        <h1>{mode === "login" ? "进入智能分析工作区" : "创建个人工作区"}</h1>
        <p>一个账号统一管理视频、文档、Agent 分析与业务行动。全流程可在本机验收，无需域名。</p>
        {externalLoginEnabled ? (
          <button className="button" type="button" disabled={busy} onClick={() => void beginOidcLogin()}>
            {busy ? <Loader2 size={16} className="spin" /> : <ShieldCheck size={16} />}
            {busy ? "正在完成统一身份登录…" : "使用统一身份登录 / 注册"}
          </button>
        ) : null}
        {localLoginEnabled ? <><div className="auth-tabs" role="tablist">
          <button className={mode === "login" ? "active" : ""} onClick={() => setMode("login")} type="button">登录</button>
          <button className={mode === "register" ? "active" : ""} onClick={() => setMode("register")} type="button">注册</button>
        </div>
        <form onSubmit={submit} className="auth-form">
          <label>用户名<input value={username} onChange={(event) => setUsername(event.target.value)} minLength={3} maxLength={50} required autoFocus /></label>
          <label>密码<input value={password} onChange={(event) => setPassword(event.target.value)} type="password" minLength={8} maxLength={72} required /></label>
          {error ? <div className="auth-error">{error}</div> : null}
          <button className="button" type="submit" disabled={busy || !username.trim() || password.length < 8}>
            {busy ? <Loader2 size={16} className="spin" /> : <KeyRound size={16} />}
            {busy ? "正在连接本地工作区…" : mode === "login" ? "登录" : "注册并创建工作区"}
          </button>
        </form></> : null}
        <footer><ShieldCheck size={15} />统一账号 · 工作区权限隔离</footer>
      </section>
    </main>
  );
}
