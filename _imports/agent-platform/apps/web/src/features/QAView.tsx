import React from "react";
import {
  Activity, AlertCircle, BarChart3, Bot, CheckCircle2, ClipboardList, Coins, Copy,
  FileText, Gauge, Loader2, RefreshCw, Send, ThumbsDown, ThumbsUp, Trash2,
  Upload, Workflow, X,
} from "lucide-react";
import {
  type ActorRole, type AnswerMode, type ChatMetricsSummary, type ChatResponse,
  type EmbeddingStatus, type RetrieverMode, type SystemStatus, type WorkflowMode,
  listDocuments, listPendingActions,
} from "../api";
import {
  MetricItem, StatusItem, UsageBars, formatCoverage, formatDate, formatDecimal,
  formatMilliseconds, formatPercent,
} from "./common";
import "../styles/qa.css";

export function QAView(props: {
  fileInputRef: React.RefObject<HTMLInputElement | null>;
  documents: Awaited<ReturnType<typeof listDocuments>>;
  selectedFile: File | null;
  question: string;
  answerMode: AnswerMode;
  retrieverMode: RetrieverMode;
  workflowMode: WorkflowMode;
  embeddingStatus: EmbeddingStatus | null;
  systemStatus: SystemStatus | null;
  metricsSummary: ChatMetricsSummary | null;
  chatResponse: ChatResponse | null;
  isLoadingDocuments: boolean;
  isUploading: boolean;
  isAsking: boolean;
  isRebuildingEmbeddings: boolean;
  deletingDocumentId: string | null;
  pendingActions: Awaited<ReturnType<typeof listPendingActions>>;
  approvingActionId: string | null;
  actorRole: ActorRole;
  answerFeedback: "up" | "down" | null;
  isSendingFeedback: boolean;
  setSelectedFile: (f: File | null) => void;
  setQuestion: (q: string) => void;
  setAnswerMode: (m: AnswerMode) => void;
  setRetrieverMode: (m: RetrieverMode) => void;
  setWorkflowMode: (m: WorkflowMode) => void;
  handleUpload: (e: React.FormEvent<HTMLFormElement>) => void;
  handleAsk: (e: React.FormEvent<HTMLFormElement>) => void;
  handleDeleteDocument: (id: string) => void;
  handleRebuildEmbeddings: () => void;
  handleCopyAnswer: () => void;
  handleApprove: (actionId: string, approved: boolean) => void;
  handleAnswerFeedback: (rating: "up" | "down") => void;
  setChatResponse: (r: ChatResponse | null) => void;
  setError: (e: string | null) => void;
}) {
  const p = props;
  return (
    <div className="two-column">
      <section className="sidebar">
        <div className="card">
          <h2>
            <FileText size={19} />
            文档管理
          </h2>
          <form className="upload-form" onSubmit={p.handleUpload}>
            <input
              ref={p.fileInputRef}
              type="file"
              accept=".txt,.md,.pdf"
              onChange={(event) => p.setSelectedFile(event.target.files?.[0] ?? null)}
              disabled={p.isUploading}
            />
            <button className="button" type="submit" disabled={p.isUploading || !p.selectedFile}>
              {p.isUploading ? (
                <>
                  <Loader2 size={14} />
                  上传中...
                </>
              ) : (
                <>
                  <Upload size={14} />
                  上传
                </>
              )}
            </button>
          </form>
          <div className="document-toolbar">
            <button
              className="icon-button subtle"
              type="button"
              onClick={() => { p.setError(null); p.handleRebuildEmbeddings(); }}
              disabled={p.isRebuildingEmbeddings || (p.systemStatus?.document_count ?? 0) === 0}
              title="一键重建所有 chunk 的本地 embedding"
            >
              <RefreshCw size={16} />
            </button>
          </div>
        </div>

        <div className="card" style={{ padding: 0 }}>
          {p.isLoadingDocuments ? (
            <div style={{ padding: "var(--space-md)" }}>
              <Loader2 size={16} /> 加载中...
            </div>
          ) : p.documents.length === 0 ? (
            <div className="empty-state">还没有上传文档。</div>
          ) : (
            <ul className="document-list">
              {p.documents.map((document) => (
                <li key={document.document_id}>
                  <div>
                    <strong>{document.filename}</strong>
                    <span>{document.chunk_count} chunk · {formatDate(document.created_at)}</span>
                  </div>
                  <button
                    className="icon-button danger"
                    type="button"
                    disabled={p.deletingDocumentId === document.document_id}
                    onClick={() => void p.handleDeleteDocument(document.document_id)}
                  >
                    {p.deletingDocumentId === document.document_id ? (
                      <Loader2 size={14} />
                    ) : (
                      <Trash2 size={14} />
                    )}
                  </button>
                </li>
              ))}
            </ul>
          )}
        </div>

        <div className="card">
          <h2>
            <Gauge size={19} />
            工程指标
          </h2>
          {p.metricsSummary ? (
            <div className="metrics-grid">
              <MetricItem label="请求量" value={p.metricsSummary.total_requests} />
              <MetricItem label="回答率" value={formatPercent(p.metricsSummary.answer_rate)} />
              <MetricItem label="拒答率" value={formatPercent(p.metricsSummary.refusal_rate)} />
              <MetricItem label="错误率" value={formatPercent(p.metricsSummary.error_rate)} />
              <MetricItem label="证据通过率" value={formatPercent(p.metricsSummary.evidence_pass_rate)} />
              <MetricItem label="引用就绪率" value={formatPercent(p.metricsSummary.citation_ready_rate)} />
              <MetricItem label="P95 延迟" value={formatMilliseconds(p.metricsSummary.p95_latency_ms)} />
              <MetricItem label="平均轮次" value={formatDecimal(p.metricsSummary.avg_retrieval_rounds)} />
            </div>
          ) : (
            <div className="empty-state">暂无指标，提问后自动更新。</div>
          )}
        </div>

        {p.metricsSummary && [p.metricsSummary.workflow_usage, p.metricsSummary.retriever_usage, p.metricsSummary.answer_mode_usage]
          .some((dimension) => Object.values(dimension ?? {}).some((count) => count > 0)) ? (
          <div className="card">
            <h2>
              <BarChart3 size={19} />
              使用分布
            </h2>
            <UsageBars title="工作流" data={p.metricsSummary.workflow_usage} color="var(--viz-blue)" />
            <UsageBars title="检索模式" data={p.metricsSummary.retriever_usage} color="var(--viz-aqua)" />
            <UsageBars title="回答模式" data={p.metricsSummary.answer_mode_usage} color="var(--viz-violet)" />
          </div>
        ) : null}

        <div className="card">
          <h2>
            <Activity size={19} />
            系统状态
          </h2>
          {p.systemStatus ? (
            <div className="status-list">
              <StatusItem label="API" value={p.systemStatus.status} ok />
              <StatusItem label="文档数" value={p.systemStatus.document_count} />
              <StatusItem label="Chunk 数" value={p.systemStatus.chunk_count} />
              <StatusItem label="LLM" value={p.systemStatus.llm_configured ? p.systemStatus.llm_provider : "未配置"} ok={p.systemStatus.llm_configured} />
              <StatusItem label="回答模式" value={p.systemStatus.default_answer_mode} />
              <StatusItem label="检索模式" value={p.systemStatus.default_retriever_mode} />
              <StatusItem label="Embedding 覆盖率" value={formatCoverage(p.systemStatus.embedding?.coverage)} ok={p.systemStatus.embedding?.coverage === 1} />
            </div>
          ) : (
            <div className="empty-state">正在获取系统状态...</div>
          )}
        </div>
      </section>

      <section className="chat-area">
        <div className="card">
          <form className="chat-form" onSubmit={p.handleAsk}>
            <div className="chat-controls">
              <div className="select-group">
                <label>
                  工作流
                  <select value={p.workflowMode} onChange={(e) => p.setWorkflowMode(e.target.value as WorkflowMode)}>
                    <option value="agentic">Agentic</option>
                    <option value="standard">Standard</option>
                  </select>
                </label>
                <label>
                  回答
                  <select value={p.answerMode} onChange={(e) => p.setAnswerMode(e.target.value as AnswerMode)}>
                    <option value="auto">auto</option>
                    <option value="local">local</option>
                    <option value="api">api</option>
                  </select>
                </label>
                <label>
                  检索
                  <select value={p.retrieverMode} onChange={(e) => p.setRetrieverMode(e.target.value as RetrieverMode)}>
                    <option value="keyword">keyword</option>
                    <option value="embedding">embedding</option>
                    <option value="hybrid">hybrid</option>
                  </select>
                </label>
              </div>
            </div>
            <div className="chat-input-row">
              <input
                placeholder="请输入企业知识库问题..."
                value={p.question}
                onChange={(event) => p.setQuestion(event.target.value)}
                disabled={p.isAsking}
              />
              <button className="button" type="submit" disabled={p.isAsking || !p.question.trim()}>
                {p.isAsking ? (
                  <>
                    <Loader2 size={15} />
                    思考中...
                  </>
                ) : (
                  <>
                    <Send size={15} />
                    提问
                  </>
                )}
              </button>
            </div>
          </form>
        </div>

        {p.chatResponse?.agent_summary ? (
          <section className="agent-summary-box">
            <h3>
              <Bot size={18} />
              Agent 执行摘要
              {p.chatResponse.agent_summary.pending_approval ? (
                <span className="pending-tag">&#x23F3; 待审批</span>
              ) : null}
            </h3>
            <div className="agent-metrics">
              <span><strong>意图</strong>{p.chatResponse.agent_summary.intent}</span>
              <span><strong>复杂度</strong>{p.chatResponse.agent_summary.complexity}</span>
              <span><strong>检索轮次</strong>{p.chatResponse.agent_summary.retrieval_rounds}</span>
              <span><strong>证据</strong>{p.chatResponse.agent_summary.evidence_status}</span>
              <span><strong>引用</strong>{p.chatResponse.agent_summary.citation_status}</span>
            </div>
            {p.chatResponse.agent_summary.tool_calls.length > 0 ? (
              <details open>
                <summary>工具调用（{p.chatResponse.agent_summary.tool_calls.length}）</summary>
                <ul className="tool-call-list">
                  {p.chatResponse.agent_summary.tool_calls.map((tc, i) => (
                    <li key={i}>
                      <span className={tc.success ? "tool-ok" : "tool-err"}>
                        {tc.success ? <CheckCircle2 size={14} /> : <AlertCircle size={14} />}
                      </span>
                      <span><strong>{tc.tool_name}</strong></span>
                      <span>{tc.result_summary}</span>
                      <span>{tc.status} · {formatMilliseconds(tc.duration_ms)}</span>
                    </li>
                  ))}
                </ul>
              </details>
            ) : null}
            {p.chatResponse.agent_summary.graph_paths.length > 0 ? (
              <details open>
                <summary>
                  关系图谱（{p.chatResponse.agent_summary.graph_paths.length} 条关系）
                </summary>
                <div className="graph-entity-chips">
                  {p.chatResponse.agent_summary.graph_entities.map((entity) => (
                    <span className="entity-chip" key={entity}>{entity}</span>
                  ))}
                </div>
                <ul className="graph-path-list">
                  {p.chatResponse.agent_summary.graph_paths.slice(0, 8).map((path, index) => (
                    <li key={`${path}-${index}`}>{path}</li>
                  ))}
                </ul>
              </details>
            ) : null}
            <details>
              <summary>查看计划 query（{p.chatResponse.agent_summary.queries.length}）</summary>
              <ol>
                {p.chatResponse.agent_summary.queries.map((query, index) => (
                  <li key={`${query}-${index}`}>{query}</li>
                ))}
              </ol>
            </details>
          </section>
        ) : null}

        {p.chatResponse?.pending_actions && p.chatResponse.pending_actions.length > 0 ? (
          <section className="pending-actions-box">
            <h3>
              <ClipboardList size={18} />
              待审批操作
            </h3>
            {p.chatResponse.pending_actions.map((action) => (
              <div className="pending-action-item" key={action.action_id}>
                <div className="pending-action-header">
                  <span className="action-type-badge">{action.action_type === "create_ticket" ? "创建工单" : "更新状态"}</span>
                  <span className="action-status pending">待审批</span>
                </div>
                <div className="pending-action-body">
                  {action.action_type === "create_ticket" ? (
                    <>
                      <p><strong>标题：</strong>{String(action.payload.title ?? "")}</p>
                      <p><strong>优先级：</strong>{String(action.payload.priority ?? "")}</p>
                      <p><strong>描述：</strong>{String(action.payload.description ?? "").slice(0, 200)}</p>
                    </>
                  ) : (
                    <>
                      <p><strong>工单：</strong>{String(action.payload.ticket_id ?? "")}</p>
                      <p><strong>目标状态：</strong>{String(action.payload.new_status ?? "")}</p>
                    </>
                  )}
                </div>
                <div className="pending-action-actions">
                  <button
                    className="button approve"
                    disabled={p.approvingActionId === action.action_id || p.actorRole === "viewer"}
                    onClick={() => void p.handleApprove(action.action_id, true)}
                  >
                    {p.approvingActionId === action.action_id ? <Loader2 size={14} /> : <ThumbsUp size={14} />}
                    批准
                  </button>
                  <button
                    className="button reject"
                    disabled={p.approvingActionId === action.action_id || p.actorRole === "viewer"}
                    onClick={() => void p.handleApprove(action.action_id, false)}
                  >
                    <ThumbsDown size={14} />
                    拒绝
                  </button>
                </div>
              </div>
            ))}
          </section>
        ) : null}

        <div className="answer-box">
          <div className="answer-title">
            <div>
              <Bot size={19} />
              <h3>回答</h3>
              {p.chatResponse?.token_usage ? (
                <span className="token-pill" title={`prompt ${p.chatResponse.token_usage.prompt_tokens} + completion ${p.chatResponse.token_usage.completion_tokens}`}>
                  <Coins size={13} />
                  {p.chatResponse.token_usage.total_tokens} tokens
                  {p.chatResponse.token_usage.estimated_cost_usd > 0
                    ? ` · $${p.chatResponse.token_usage.estimated_cost_usd.toFixed(5)}`
                    : ""}
                </span>
              ) : null}
            </div>
            <div className="answer-actions">
              <button
                className={"icon-button subtle feedback" + (p.answerFeedback === "up" ? " active-up" : "")}
                type="button"
                onClick={() => void p.handleAnswerFeedback("up")}
                disabled={!p.chatResponse?.log_id || p.isSendingFeedback || p.answerFeedback !== null}
                title={p.answerFeedback === "up" ? "已标记有帮助" : "答案有帮助"}
              >
                <ThumbsUp size={16} />
              </button>
              <button
                className={"icon-button subtle feedback" + (p.answerFeedback === "down" ? " active-down" : "")}
                type="button"
                onClick={() => void p.handleAnswerFeedback("down")}
                disabled={!p.chatResponse?.log_id || p.isSendingFeedback || p.answerFeedback !== null}
                title={p.answerFeedback === "down" ? "已标记待改进" : "答案待改进"}
              >
                <ThumbsDown size={16} />
              </button>
              <button
                className="icon-button subtle"
                type="button"
                onClick={() => void p.handleCopyAnswer()}
                disabled={!p.chatResponse?.answer}
                title="复制回答"
              >
                <Copy size={16} />
              </button>
              <button
                className="icon-button subtle"
                type="button"
                onClick={() => p.setChatResponse(null)}
                disabled={!p.chatResponse}
                title="清空回答"
              >
                <X size={16} />
              </button>
            </div>
          </div>
          <pre>{p.chatResponse?.answer ?? "回答会显示在这里。"}</pre>
          {p.answerFeedback ? (
            <div className="feedback-ack">
              <CheckCircle2 size={14} />
              反馈已记录，会体现在运行监控的满意度指标中。
            </div>
          ) : null}
        </div>

        <div className="sources-box">
          <div className="sources-title">
            <h3>来源证据</h3>
            <span>{p.chatResponse?.sources.length ?? 0} 条</span>
          </div>
          {!p.chatResponse || p.chatResponse.sources.length === 0 ? (
            <div className="empty-source">暂无来源。上传文档并提问后，这里会显示命中的 chunk。</div>
          ) : (
            p.chatResponse.sources.map((source, index) => (
              <article className="source-item" key={`${source.document_id}-${source.chunk_index}`}>
                <header>
                  <strong>来源 {index + 1}</strong>
                  <span>
                    {source.filename} · chunk {source.chunk_index} · score {source.score}
                  </span>
                </header>
                <p>{source.content}</p>
              </article>
            ))
          )}
        </div>

        <div className="trace-box">
          <div className="answer-title">
            <div>
              <Workflow size={19} />
              <h3>执行轨迹</h3>
            </div>
          </div>
          {!p.chatResponse || p.chatResponse.trace.length === 0 ? (
            <div className="empty-source">暂无轨迹。提问后，这里会显示检索和回答路径。</div>
          ) : (
            <ol className="trace-list">
              {p.chatResponse.trace.map((step, index) => (
                <li className="trace-item" key={`${step.name}-${index}`}>
                  <div>
                    <strong>{step.name}</strong>
                    <span>{step.status}</span>
                  </div>
                  <p>{step.detail}</p>
                </li>
              ))}
            </ol>
          )}
        </div>
      </section>
    </div>
  );
}
