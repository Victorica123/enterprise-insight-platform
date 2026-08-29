import React from "react";
import { AlertCircle, CheckCircle2, FileCheck2, Loader2, Play, Send, ShieldCheck, Sparkles } from "lucide-react";
import {
  type AnalysisAuditEvent, type AnalysisSession, approvePrdPublication,
  confirmAnalysisSession, createAnalysisSession, listAnalysisAudit,
  listAnalysisSessions, listPublicationQueue, requestPrdPublication,
} from "../analysisApi";
import { loadSession } from "../session";
import { formatTimestamp } from "./MediaWorkspace";
import { formatDate, getErrorMessage } from "./common";
import "../styles/analysis.css";

const STAGE_NAMES: Record<string, string> = {
  intent: "1 · 意图识别", stakeholders: "2 · 干系人", domain: "3 · 领域深挖",
  risks: "4 · 异常与风险", convergence: "5 · 收敛检查", prd: "6 · PRD 草稿",
};

export function AnalysisWorkspace(props: {
  selectedAssetIds: string[];
  onPlayEvidence: (assetId: string, startMs: number) => void;
  onError: (message: string) => void;
}) {
  const [objective, setObjective] = React.useState("基于选定访谈，生成可评审的产品需求文档");
  const [sessions, setSessions] = React.useState<AnalysisSession[]>([]);
  const [active, setActive] = React.useState<AnalysisSession | null>(null);
  const [answers, setAnswers] = React.useState<Record<string, string>>({});
  const [audit, setAudit] = React.useState<AnalysisAuditEvent[]>([]);
  const [busy, setBusy] = React.useState(false);
  const viewer = loadSession();

  const refresh = React.useCallback(async () => {
    try {
      const own = await listAnalysisSessions();
      const queue = viewer?.role === "viewer" ? [] : await listPublicationQueue();
      const next = [...own, ...queue.filter((candidate) => !own.some((item) => item.session_id === candidate.session_id))];
      setSessions(next);
      setActive((current) => current ? next.find((item) => item.session_id === current.session_id) ?? current : next[0] ?? null);
    } catch (caught) { props.onError(getErrorMessage(caught)); }
  }, [props.onError, viewer?.role]);

  React.useEffect(() => { void refresh(); }, [refresh]);

  React.useEffect(() => {
    if (!active || active.owner_id !== viewer?.userId) { setAudit([]); return; }
    void listAnalysisAudit(active.session_id).then(setAudit).catch((caught) => props.onError(getErrorMessage(caught)));
  }, [active?.session_id, active?.owner_id, props.onError, viewer?.userId]);

  async function create(event: React.FormEvent) {
    event.preventDefault(); setBusy(true);
    try {
      const created = await createAnalysisSession(objective.trim(), props.selectedAssetIds);
      setActive(created); setSessions((current) => [created, ...current]); setAnswers({});
    } catch (caught) { props.onError(getErrorMessage(caught)); }
    finally { setBusy(false); }
  }

  async function confirm(event: React.FormEvent) {
    event.preventDefault();
    if (!active?.resume_token) return;
    setBusy(true);
    try {
      const updated = await confirmAnalysisSession(active.session_id, active.resume_token, answers);
      setActive(updated); setSessions((current) => current.map((item) => item.session_id === updated.session_id ? updated : item));
      setAnswers({});
    } catch (caught) { props.onError(getErrorMessage(caught)); }
    finally { setBusy(false); }
  }

  function replaceSession(updated: AnalysisSession) {
    setActive(updated);
    setSessions((current) => current.map((item) => item.session_id === updated.session_id ? updated : item));
    if (updated.owner_id === viewer?.userId) {
      void listAnalysisAudit(updated.session_id).then(setAudit).catch((caught) => props.onError(getErrorMessage(caught)));
    }
  }

  async function requestPublication() {
    if (!active) return;
    setBusy(true);
    try { replaceSession(await requestPrdPublication(active.session_id)); }
    catch (caught) { props.onError(getErrorMessage(caught)); }
    finally { setBusy(false); }
  }

  async function approvePublication() {
    if (!active?.publication?.approval_token) return;
    setBusy(true);
    try {
      replaceSession(await approvePrdPublication(
        active.session_id, active.publication.request_id, active.publication.approval_token,
      ));
    } catch (caught) { props.onError(getErrorMessage(caught)); }
    finally { setBusy(false); }
  }

  return <div className="analysis-layout">
    <aside className="analysis-sidebar">
      <section className="card">
        <span className="eyebrow">EVIDENCE-FIRST DELIVERY</span>
        <h2><Sparkles size={20} />六阶段需求分析</h2>
        <form className="analysis-create" onSubmit={create}>
          <textarea value={objective} onChange={(event) => setObjective(event.target.value)} rows={4} maxLength={1000} />
          <div className="analysis-scope">范围：{props.selectedAssetIds.length ? `${props.selectedAssetIds.length} 个已选视频` : "当前用户全部授权证据"}</div>
          <button className="button" disabled={busy || objective.trim().length < 3}>{busy ? <Loader2 className="spin" size={15} /> : <Send size={15} />}开始分析</button>
        </form>
      </section>
      <section className="card analysis-history"><h3>分析记录</h3>{sessions.length ? sessions.map((session) =>
        <button key={session.session_id} className={active?.session_id === session.session_id ? "active" : ""} onClick={() => { setActive(session); setAnswers({}); }}>
          <strong>{session.objective}</strong><span>{session.owner_id !== viewer?.userId ? "待我审批 · " : ""}{statusName(session.status)} · {formatDate(session.created_at)}</span>
        </button>) : <div className="empty-state">暂无分析记录</div>}</section>
    </aside>
    <section className="analysis-main">
      {!active ? <div className="card empty-state"><FileCheck2 size={34} /><p>选择证据并启动分析。系统会在事实不足时停下来向你确认。</p></div> : <>
        <section className="card analysis-header"><div><span className="eyebrow">{active.status}</span><h2>{active.objective}</h2></div><span>阶段 {active.current_stage}/6</span></section>
        <div className="stage-grid">{active.stages.map((stage) => <article className={`card stage-card ${stage.status === "WAITING_CONFIRMATION" ? "waiting" : ""}`} key={stage.stage}>
          <header>{stage.status === "COMPLETED" ? <CheckCircle2 size={17} /> : <AlertCircle size={17} />}<strong>{STAGE_NAMES[stage.stage]}</strong></header>
          <p>{stage.summary}</p>
          {stage.findings.length ? <ul>{stage.findings.map((finding) => <li key={finding}>{finding}</li>)}</ul> : null}
          {stage.evidence.length ? <details><summary>{stage.evidence.length} 条证据</summary>{stage.evidence.map((evidence, index) => <div className="analysis-evidence" key={`${evidence.document_id}-${evidence.chunk_index}-${index}`}>
            <span>{evidence.filename}{evidence.source_type === "video" && evidence.start_ms != null ? ` · ${formatTimestamp(evidence.start_ms)}` : ""}</span><p>{evidence.excerpt}</p>
            {evidence.asset_id && evidence.start_ms != null ? <button onClick={() => props.onPlayEvidence(evidence.asset_id!, evidence.start_ms!)}><Play size={13} />回放证据</button> : null}
          </div>)}</details> : null}
        </article>)}</div>
        {active.status === "WAITING_CONFIRMATION" ? <form className="card confirmation-card" onSubmit={confirm}>
          <h3>需要你的业务判断</h3><p>这些信息会作为“已确认事实”写入本次会话，然后从收敛检查继续，不会重跑历史步骤。</p>
          {active.open_questions.map((question) => <label key={question.question_id}><strong>{question.question}</strong><span>{question.reason}</span><textarea required value={answers[question.question_id] ?? ""} onChange={(event) => setAnswers({ ...answers, [question.question_id]: event.target.value })} /></label>)}
          <button className="button" disabled={busy || active.open_questions.some((question) => !(answers[question.question_id] ?? "").trim())}>{busy ? <Loader2 className="spin" size={15} /> : <Send size={15} />}确认并继续</button>
        </form> : null}
        {active.prd ? <section className="card prd-draft"><header><div><span className="eyebrow">证据化 PRD</span><h2>{active.prd.title}</h2></div><span className="task-status">{active.prd.publication_status}</span></header><p>{active.prd.executive_summary}</p>
          <h3>需求与验收</h3>{active.prd.requirements.map((requirement) => <article key={requirement.requirement_id}><strong>{requirement.requirement_id} · {requirement.title}</strong><p>{requirement.description}</p><ul>{requirement.acceptance_criteria.map((item) => <li key={item}>验收：{item}</li>)}{requirement.assumptions.map((item) => <li className="assumption" key={item}>假设：{item}</li>)}</ul></article>)}
          <PublicationControls active={active} viewerId={viewer?.userId ?? ""} busy={busy} onRequest={requestPublication} onApprove={approvePublication} />
          {audit.length ? <div className="publication-audit"><strong><ShieldCheck size={14} />发布审计</strong>{audit.map((event) => <span key={event.event_id}>{event.action === "PUBLICATION_REQUESTED" ? "申请发布" : "批准发布"} · {event.actor_id} · {formatDate(event.created_at)}</span>)}</div> : null}
        </section> : null}
      </>}
    </section>
  </div>;
}

function statusName(status: AnalysisSession["status"]): string {
  return { RUNNING: "运行中", WAITING_CONFIRMATION: "待确认", DRAFT_READY: "草稿就绪", PUBLISH_PENDING: "待发布审批", PUBLISHED: "已发布", FAILED: "失败" }[status];
}

function PublicationControls(props: {
  active: AnalysisSession;
  viewerId: string;
  busy: boolean;
  onRequest: () => void;
  onApprove: () => void;
}) {
  if (props.active.status === "DRAFT_READY") return <div className="publication-note">
    <span>发布不会自动发生。个人空间需要再次确认；团队空间需要另一位成员审批。</span>
    <button className="button" disabled={props.busy} onClick={props.onRequest}>申请正式发布</button>
  </div>;
  if (props.active.status === "PUBLISH_PENDING" && props.active.publication) {
    const personal = props.active.publication.policy === "OWNER_RECONFIRMATION";
    const canApprove = personal
      ? props.active.owner_id === props.viewerId
      : props.active.publication.requested_by !== props.viewerId;
    return <div className="publication-note">
      <span>{personal ? "这是第二次独立确认。确认后 PRD 将进入正式发布态并记录审计。" : canApprove ? "团队四眼审批：你不是提交者，可以完成审批。" : "已提交，等待另一位团队成员审批。"}</span>
      {canApprove ? <button className="button" disabled={props.busy} onClick={props.onApprove}>确认正式发布</button> : null}
    </div>;
  }
  if (props.active.status === "PUBLISHED") return <div className="publication-note published"><ShieldCheck size={16} />已完成审批并正式发布，审计记录不可随草稿覆盖。</div>;
  return null;
}
