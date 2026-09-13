import React from "react";
import { AlertCircle, BookCheck, CheckCircle2, FileCheck2, ListTodo, Loader2, Play, Send, ShieldCheck, Sparkles } from "lucide-react";
import {
  type AnalysisSession,
  approvePrdPublication, confirmAnalysisSession, createActionTicketDraft,
  createAnalysisSession, decideKnowledgeCandidate, decideKnowledgeLifecycle,
  requestKnowledgeLifecycle, requestPrdPublication,
} from "../analysisApi";
import { useAnalysisData } from "../hooks/useAnalysisData";
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
  const { viewer, sessions, setSessions, active, setActive, audit, deliverables, setDeliverables,
    refreshAudit, refreshRelated, refreshDeliverables } = useAnalysisData(props.onError);
  const [objective, setObjective] = React.useState("基于选定访谈，生成可评审的产品需求文档");
  const [answers, setAnswers] = React.useState<Record<string, string>>({});
  const [lifecycleDrafts, setLifecycleDrafts] = React.useState<Record<string, { reason: string; statement: string }>>({});
  const [busy, setBusy] = React.useState(false);
  const canWrite = viewer.role !== "viewer";

  async function create(event: React.FormEvent) {
    event.preventDefault();
    if (!canWrite) return;
    setBusy(true);
    try {
      const created = await createAnalysisSession(objective.trim(), props.selectedAssetIds);
      setActive(created); setSessions((current) => [created, ...current]); setAnswers({});
    } catch (caught) { props.onError(getErrorMessage(caught)); }
    finally { setBusy(false); }
  }

  async function confirm(event: React.FormEvent) {
    event.preventDefault();
    if (!canWrite || !active?.resume_token) return;
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
      void refreshAudit();
    }
  }

  async function requestPublication() {
    if (!canWrite || !active) return;
    setBusy(true);
    try { replaceSession(await requestPrdPublication(active.session_id)); }
    catch (caught) { props.onError(getErrorMessage(caught)); }
    finally { setBusy(false); }
  }

  async function approvePublication() {
    if (!canWrite || !active?.publication?.approval_token) return;
    setBusy(true);
    try {
      replaceSession(await approvePrdPublication(
        active.session_id, active.publication.request_id, active.publication.approval_token,
      ));
    } catch (caught) { props.onError(getErrorMessage(caught)); }
    finally { setBusy(false); }
  }

  async function decideCandidate(candidateId: string, approved: boolean) {
    if (!canWrite || !active) return;
    setBusy(true);
    try {
      const updated = await decideKnowledgeCandidate(active.session_id, candidateId, approved);
      setDeliverables((current) => current ? {
        ...current,
        knowledge_candidates: current.knowledge_candidates.map((item) =>
          item.candidate_id === updated.candidate_id ? updated : item),
      } : current);
      void refreshRelated();
    } catch (caught) { props.onError(getErrorMessage(caught)); }
    finally { setBusy(false); }
  }

  async function requestLifecycle(candidateId: string, action: "REVOKE" | "SUPERSEDE") {
    if (!canWrite || !active || !deliverables) return;
    const candidate = deliverables.knowledge_candidates.find((item) => item.candidate_id === candidateId);
    const draft = lifecycleDrafts[candidateId] ?? { reason: "", statement: "" };
    if (!candidate || draft.reason.trim().length < 3) {
      props.onError("请填写至少 3 个字符的治理原因。"); return;
    }
    if (action === "SUPERSEDE" && draft.statement.trim().length < 3) {
      props.onError("请填写替代后的知识陈述。"); return;
    }
    setBusy(true);
    try {
      await requestKnowledgeLifecycle(active.session_id, candidateId, {
        action,
        reason: draft.reason.trim(),
        replacement_statement: action === "SUPERSEDE" ? draft.statement.trim() : undefined,
        replacement_evidence: action === "SUPERSEDE" ? candidate.evidence : undefined,
      });
      await refreshDeliverables();
      void refreshRelated();
      setLifecycleDrafts((current) => ({ ...current, [candidateId]: { reason: "", statement: "" } }));
    } catch (caught) { props.onError(getErrorMessage(caught)); }
    finally { setBusy(false); }
  }

  async function reviewLifecycle(candidateId: string, requestId: string, approved: boolean) {
    if (!canWrite || !active) return;
    setBusy(true);
    try {
      await decideKnowledgeLifecycle(active.session_id, candidateId, requestId, approved);
      await refreshDeliverables();
      void refreshRelated();
    } catch (caught) { props.onError(getErrorMessage(caught)); }
    finally { setBusy(false); }
  }

  async function draftActionTicket(actionItemId: string) {
    if (!canWrite || !active) return;
    setBusy(true);
    try {
      const updated = await createActionTicketDraft(active.session_id, actionItemId);
      setDeliverables((current) => current ? {
        ...current,
        action_items: current.action_items.map((item) =>
          item.action_item_id === updated.action_item.action_item_id ? updated.action_item : item),
      } : current);
      void refreshRelated();
    } catch (caught) { props.onError(getErrorMessage(caught)); }
    finally { setBusy(false); }
  }

  return <div className="analysis-layout">
    <aside className="analysis-sidebar">
      <section className="card">
        <span className="eyebrow">EVIDENCE-FIRST DELIVERY</span>
        <h2><Sparkles size={20} />六阶段需求分析</h2>
        <form className="analysis-create" onSubmit={create}>
          <textarea disabled={!canWrite} value={objective} onChange={(event) => setObjective(event.target.value)} rows={4} maxLength={1000} />
          <div className="analysis-scope">范围：{props.selectedAssetIds.length ? `${props.selectedAssetIds.length} 个已选视频` : "当前用户全部授权证据"}</div>
          <button className="button" disabled={!canWrite || busy || objective.trim().length < 3}>{busy ? <Loader2 className="spin" size={15} /> : <Send size={15} />}开始分析</button>
          {!canWrite ? <p>当前角色为只读，可查看已有分析与发布结果。</p> : null}
        </form>
      </section>
      <section className="card analysis-history"><h3>分析记录</h3>{sessions.length ? sessions.map((session) =>
        <button key={session.session_id} className={active?.session_id === session.session_id ? "active" : ""} onClick={() => { setActive(session); setAnswers({}); }}>
          <strong>{session.objective}</strong><span>{session.owner_id !== viewer?.userId ? "待我审批 · " : ""}{statusName(session.status)} · {formatDate(session.created_at)}</span>
        </button>) : <div className="empty-state">暂无分析记录</div>}</section>
    </aside>
    <section className="analysis-main">
      {!active ? <div className="card empty-state"><FileCheck2 size={34} /><p>{canWrite ? "选择证据并启动分析。系统会在事实不足时停下来向你确认。" : "当前工作区还没有可查看的分析记录。"}</p></div> : <>
        <section className="card analysis-header"><div><span className="eyebrow">{active.status}</span><h2>{active.objective}</h2></div><div className="analysis-provenance"><span>阶段 {active.current_stage}/6 · 检查点 v{active.checkpoint_version}</span><code title={active.evidence_snapshot_sha256}>hybrid · rev {active.evidence_revision} · {active.evidence_snapshot_sha256.slice(0, 12)}</code></div></section>
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
          {active.open_questions.map((question) => <label key={question.question_id}><strong>{question.question}</strong><span>{question.reason}</span><textarea disabled={!canWrite} required value={answers[question.question_id] ?? ""} onChange={(event) => setAnswers({ ...answers, [question.question_id]: event.target.value })} /></label>)}
          <button className="button" disabled={!canWrite || busy || active.open_questions.some((question) => !(answers[question.question_id] ?? "").trim())}>{busy ? <Loader2 className="spin" size={15} /> : <Send size={15} />}确认并继续</button>
        </form> : null}
        {active.prd ? <section className="card prd-draft"><header><div><span className="eyebrow">证据化 PRD</span><h2>{active.prd.title}</h2></div><span className="task-status">{active.prd.publication_status}</span></header><p>{active.prd.executive_summary}</p>
          <h3>需求与验收</h3>{active.prd.requirements.map((requirement) => <article key={requirement.requirement_id}><strong>{requirement.requirement_id} · {requirement.title}</strong><p>{requirement.description}</p><ul>{requirement.acceptance_criteria.map((item) => <li key={item}>验收：{item}</li>)}{requirement.assumptions.map((item) => <li className="assumption" key={item}>假设：{item}</li>)}</ul></article>)}
          <PublicationControls active={active} viewerId={viewer.userId} canWrite={canWrite} busy={busy} onRequest={requestPublication} onApprove={approvePublication} />
          {audit.length ? <div className="publication-audit"><strong><ShieldCheck size={14} />发布审计</strong>{audit.map((event) => <span key={event.event_id}>{event.action === "PUBLICATION_REQUESTED" ? "申请发布" : "批准发布"} · {event.actor_id} · {formatDate(event.created_at)}</span>)}</div> : null}
        </section> : null}
        {deliverables ? <section className="card publication-deliverables">
          <header><div><span className="eyebrow">PUBLISHED DELIVERY</span><h2><FileCheck2 size={19} />发布交付物</h2></div><code>v{deliverables.version.version_number} · {deliverables.version.content_sha256.slice(0, 12)}</code></header>
          <p>PRD 已保存为不可变快照。知识候选批准后才沉淀为可检索知识；行动项批准后才创建工单。</p>
          <div className="delivery-grid">
            <div><h3><BookCheck size={16} />知识候选与版本治理</h3>{deliverables.knowledge_candidates.map((candidate) => {
              const canDecide = candidate.status === "PENDING" && viewer?.role !== "viewer"
                && (viewer?.workspaceType === "personal" ? candidate.owner_id === viewer?.userId : candidate.created_by !== viewer?.userId);
              const versions = deliverables.knowledge_versions.filter((item) => item.candidate_id === candidate.candidate_id);
              const lifecycle = deliverables.knowledge_lifecycle_requests.filter((item) => item.candidate_id === candidate.candidate_id);
              const pending = lifecycle.find((item) => item.status === "PENDING");
              const canGovern = candidate.status === "APPROVED" && candidate.knowledge_status === "ACTIVE"
                && !pending && viewer?.role !== "viewer";
              const canReview = Boolean(pending && viewer?.role !== "viewer"
                && (viewer?.workspaceType === "personal" || pending.requested_by !== viewer?.userId));
              const draft = lifecycleDrafts[candidate.candidate_id] ?? { reason: "", statement: "" };
              return <article key={candidate.candidate_id} className="knowledge-governance-item">
                <strong>{candidate.requirement_id}</strong><p>{candidate.statement}</p>
                <div className="knowledge-status-row"><span className="task-status">{candidate.status}</span><span className={`task-status lifecycle-${candidate.knowledge_status.toLowerCase()}`}>{candidate.knowledge_status}{candidate.knowledge_version_number ? ` · v${candidate.knowledge_version_number}` : ""}</span></div>
                {candidate.knowledge_document_id ? <p className="mono">当前版本 · {candidate.knowledge_document_id.slice(0, 28)} · {candidate.knowledge_content_sha256?.slice(0, 12)}</p> : null}
                {versions.length ? <details className="knowledge-lineage"><summary>版本链 · {versions.length} 个不可变版本</summary>{versions.map((version) => <div key={version.knowledge_version_id} className="knowledge-version-row"><span>v{version.version_number} · {version.status}</span><code>{version.content_sha256.slice(0, 12)}</code><p>{version.statement}</p>{version.invalidation_reason ? <small>失效原因：{version.invalidation_reason}</small> : null}</div>)}</details> : null}
                {pending ? <div className="lifecycle-pending"><strong>{pending.action === "REVOKE" ? "撤回" : "替代"}申请待审批</strong><p>{pending.reason}</p><small>申请人：{pending.requested_by} · {formatDate(pending.requested_at)}</small>{canReview ? <div className="delivery-actions"><button disabled={busy} onClick={() => void reviewLifecycle(candidate.candidate_id, pending.request_id, true)}>批准治理</button><button disabled={busy} onClick={() => void reviewLifecycle(candidate.candidate_id, pending.request_id, false)}>拒绝</button></div> : <p className="governance-hint">团队空间必须由另一位写成员审批。</p>}</div> : null}
                {canGovern ? <div className="lifecycle-editor"><label>治理原因<input value={draft.reason} maxLength={1000} onChange={(event) => setLifecycleDrafts((current) => ({ ...current, [candidate.candidate_id]: { ...draft, reason: event.target.value } }))} placeholder="为什么需要撤回或替代" /></label><label>替代陈述（仅替代时必填）<textarea rows={3} maxLength={4000} value={draft.statement} onChange={(event) => setLifecycleDrafts((current) => ({ ...current, [candidate.candidate_id]: { ...draft, statement: event.target.value } }))} placeholder="新版本沿用该候选的原始证据，并形成新旧版本链" /></label><div className="delivery-actions"><button disabled={busy} onClick={() => void requestLifecycle(candidate.candidate_id, "SUPERSEDE")}>申请替代</button><button className="danger-subtle" disabled={busy} onClick={() => void requestLifecycle(candidate.candidate_id, "REVOKE")}>申请撤回</button></div></div> : null}
                {canDecide ? <div className="delivery-actions"><button disabled={busy} onClick={() => void decideCandidate(candidate.candidate_id, true)}>批准并沉淀</button><button disabled={busy} onClick={() => void decideCandidate(candidate.candidate_id, false)}>拒绝</button></div> : null}
              </article>;
            })}</div>
            <div><h3><ListTodo size={16} />行动项草稿</h3>{deliverables.action_items.map((item) => <article key={item.action_item_id}><strong>{item.title}</strong><p>{item.description}</p><span className="task-status">{item.status}</span>{item.ticket_id ? <p className="mono">工单 {item.ticket_id}</p> : null}{item.status === "DRAFT" && canWrite && item.owner_id === viewer?.userId ? <div className="delivery-actions"><button disabled={busy} onClick={() => void draftActionTicket(item.action_item_id)}>进入工单审批</button></div> : null}</article>)}</div>
          </div>
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
  canWrite: boolean;
  busy: boolean;
  onRequest: () => void;
  onApprove: () => void;
}) {
  if (props.active.status === "DRAFT_READY") return <div className="publication-note">
    <span>发布不会自动发生。个人空间需要再次确认；团队空间需要另一位成员审批。</span>
    <button className="button" disabled={!props.canWrite || props.busy} onClick={props.onRequest}>申请正式发布</button>
  </div>;
  if (props.active.status === "PUBLISH_PENDING" && props.active.publication) {
    const personal = props.active.publication.policy === "OWNER_RECONFIRMATION";
    const canApprove = props.canWrite && (personal
      ? props.active.owner_id === props.viewerId
      : props.active.publication.requested_by !== props.viewerId);
    return <div className="publication-note">
      <span>{personal ? "这是第二次独立确认。确认后 PRD 将进入正式发布态并记录审计。" : canApprove ? "团队四眼审批：你不是提交者，可以完成审批。" : "已提交，等待另一位团队成员审批。"}</span>
      {canApprove ? <button className="button" disabled={props.busy} onClick={props.onApprove}>确认正式发布</button> : null}
    </div>;
  }
  if (props.active.status === "PUBLISHED") return <div className="publication-note published"><ShieldCheck size={16} />已完成审批并正式发布，审计记录不可随草稿覆盖。</div>;
  return null;
}
