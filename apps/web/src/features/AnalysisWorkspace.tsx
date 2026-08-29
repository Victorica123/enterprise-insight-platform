import React from "react";
import { AlertCircle, CheckCircle2, FileCheck2, Loader2, Play, Send, Sparkles } from "lucide-react";
import {
  type AnalysisSession, confirmAnalysisSession, createAnalysisSession, listAnalysisSessions,
} from "../analysisApi";
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
  const [busy, setBusy] = React.useState(false);

  const refresh = React.useCallback(async () => {
    try {
      const next = await listAnalysisSessions();
      setSessions(next);
      setActive((current) => current ? next.find((item) => item.session_id === current.session_id) ?? current : next[0] ?? null);
    } catch (caught) { props.onError(getErrorMessage(caught)); }
  }, [props.onError]);

  React.useEffect(() => { void refresh(); }, [refresh]);

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
          <strong>{session.objective}</strong><span>{statusName(session.status)} · {formatDate(session.created_at)}</span>
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
        {active.prd ? <section className="card prd-draft"><header><div><span className="eyebrow">未发布草稿</span><h2>{active.prd.title}</h2></div><span className="task-status">DRAFT</span></header><p>{active.prd.executive_summary}</p>
          <h3>需求与验收</h3>{active.prd.requirements.map((requirement) => <article key={requirement.requirement_id}><strong>{requirement.requirement_id} · {requirement.title}</strong><p>{requirement.description}</p><ul>{requirement.acceptance_criteria.map((item) => <li key={item}>验收：{item}</li>)}{requirement.assumptions.map((item) => <li className="assumption" key={item}>假设：{item}</li>)}</ul></article>)}
          <div className="publication-note">正式发布规则等待 Workspace 审批策略确认；当前草稿不会静默进入正式知识库。</div>
        </section> : null}
      </>}
    </section>
  </div>;
}

function statusName(status: AnalysisSession["status"]): string {
  return { RUNNING: "运行中", WAITING_CONFIRMATION: "待确认", DRAFT_READY: "草稿就绪", FAILED: "失败" }[status];
}
