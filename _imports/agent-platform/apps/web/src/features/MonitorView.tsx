import React from "react";
import {
  Coins, Gauge, Loader2, RefreshCw, ScrollText, ThumbsDown, ThumbsUp, Workflow,
} from "lucide-react";
import {
  type ActorRole, type ChatLog, type ChatLogDetail, type ChatMetricsSummary, type TraceStep,
  getChatLogDetail, isPermissionError, listChatLogs,
} from "../api";
import {
  MetricItem, UsageBars, formatDate, formatDecimal, formatMilliseconds,
  formatPercent, formatUsd,
} from "./common";

const OUTCOME_LABELS: Record<string, string> = { answered: "已回答", refused: "已拒答", error: "错误" };

export function MonitorView({ metricsSummary, onRefresh, actorRole }: {
  metricsSummary: ChatMetricsSummary | null;
  onRefresh: () => void | Promise<void>;
  actorRole: ActorRole;
}) {
  const [logs, setLogs] = React.useState<ChatLog[]>([]);
  const [outcomeFilter, setOutcomeFilter] = React.useState("");
  const [expandedId, setExpandedId] = React.useState<number | null>(null);
  const [expandedDetail, setExpandedDetail] = React.useState<ChatLogDetail | null>(null);
  const [isLoadingLogs, setIsLoadingLogs] = React.useState(false);
  const [logsPermissionHint, setLogsPermissionHint] = React.useState<string | null>(null);

  const refreshLogs = React.useCallback(async () => {
    setIsLoadingLogs(true);
    try {
      setLogs(await listChatLogs(outcomeFilter, 50, actorRole));
      setLogsPermissionHint(null);
    } catch (caught) {
      // viewer 角色无权读取请求日志时提示切换角色；其余错误静默（服务可能未启动）
      setLogsPermissionHint(
        isPermissionError(caught) ? "当前角色（viewer）无权查看请求日志，请在右上角切换为 operator 或 admin。" : null,
      );
    } finally {
      setIsLoadingLogs(false);
    }
  }, [outcomeFilter, actorRole]);

  React.useEffect(() => {
    void refreshLogs();
  }, [refreshLogs]);

  async function toggleExpand(logId: number) {
    if (expandedId === logId) {
      setExpandedId(null);
      setExpandedDetail(null);
      return;
    }
    setExpandedId(logId);
    setExpandedDetail(null);
    try {
      setExpandedDetail(await getChatLogDetail(logId, actorRole));
    } catch {
      setExpandedDetail(null);
    }
  }

  const summary = metricsSummary;
  return (
    <div className="monitor-container">
      <section className="v3-metrics-band">
        <MetricItem label="请求量" value={summary?.total_requests ?? 0} />
        <MetricItem label="回答率" value={formatPercent(summary?.answer_rate)} />
        <MetricItem label="错误率" value={formatPercent(summary?.error_rate)} />
        <MetricItem label="P95 延迟" value={formatMilliseconds(summary?.p95_latency_ms)} />
        <MetricItem label="平均 token" value={formatDecimal(summary?.avg_tokens_per_request)} />
        <MetricItem label="累计成本" value={formatUsd(summary?.total_estimated_cost_usd)} />
        <MetricItem
          label="满意度"
          value={summary && summary.feedback_count > 0 ? formatPercent(summary.satisfaction_rate) : "—"}
        />
      </section>

      <div className="monitor-grid">
        <section className="card">
          <h2>
            <Coins size={19} />
            Token 与成本
          </h2>
          {summary && summary.total_tokens > 0 ? (
            <>
              <div className="metrics-grid">
                <MetricItem label="累计 token" value={summary.total_tokens.toLocaleString()} />
                <MetricItem label="Prompt" value={summary.total_prompt_tokens.toLocaleString()} />
                <MetricItem label="Completion" value={summary.total_completion_tokens.toLocaleString()} />
                <MetricItem label="平均成本/请求" value={formatUsd(summary.avg_cost_per_request_usd)} />
              </div>
              <UsageBars title="Token 分布（按回答模式）" data={summary.tokens_by_answer_mode} color="var(--viz-blue)" />
              <div className="cost-rows">
                {Object.entries(summary.cost_by_answer_mode).map(([mode, cost]) => (
                  <div className="cost-row" key={mode}>
                    <span>{mode}</span>
                    <span>{cost > 0 ? formatUsd(cost) : "$0（本地推理）"}</span>
                  </div>
                ))}
              </div>
            </>
          ) : (
            <div className="empty-state">暂无 token 记录，提问后自动累计。</div>
          )}
        </section>

        <section className="card">
          <h2>
            <Gauge size={19} />
            延迟与反馈
          </h2>
          {summary ? (
            <>
              <div className="metrics-grid">
                <MetricItem label="平均延迟" value={formatMilliseconds(summary.avg_latency_ms)} />
                <MetricItem label="平均轮次" value={formatDecimal(summary.avg_retrieval_rounds)} />
                <MetricItem label="正向反馈" value={summary.positive_feedback} />
                <MetricItem label="负向反馈" value={summary.negative_feedback} />
              </div>
              <div className="cost-rows">
                {Object.entries(summary.avg_latency_by_workflow).map(([workflow, latency]) => (
                  <div className="cost-row" key={workflow}>
                    <span>{workflow} 工作流</span>
                    <span>{formatMilliseconds(latency)}</span>
                  </div>
                ))}
              </div>
            </>
          ) : (
            <div className="empty-state">暂无指标。</div>
          )}
        </section>
      </div>

      <section className="card">
        <h2>
          <ScrollText size={19} />
          请求日志与回放
          <span className="count-badge">{logs.length}</span>
          {isLoadingLogs ? <Loader2 size={16} className="spin" /> : null}
          <span className="graph-toolbar">
            <select
              value={outcomeFilter}
              onChange={(event) => setOutcomeFilter(event.target.value)}
              aria-label="按结果过滤"
            >
              <option value="">全部结果</option>
              <option value="answered">已回答</option>
              <option value="refused">已拒答</option>
              <option value="error">错误</option>
            </select>
            <button
              className="icon-button subtle"
              type="button"
              onClick={() => { void refreshLogs(); void onRefresh(); }}
              title="刷新日志与指标"
            >
              <RefreshCw size={16} />
            </button>
          </span>
        </h2>
        {logsPermissionHint ? (
          <div className="empty-state">{logsPermissionHint}</div>
        ) : logs.length === 0 ? (
          <div className="empty-state">暂无请求日志。提问后这里会记录问题、结果、token 与轨迹。</div>
        ) : (
          <div className="ticket-table-wrapper">
            <table className="ticket-table log-table">
              <thead>
                <tr>
                  <th>时间</th><th>问题</th><th>结果</th><th>意图</th>
                  <th>延迟</th><th>tokens</th><th>反馈</th><th>回放</th>
                </tr>
              </thead>
              <tbody>
                {logs.map((log) => (
                  <React.Fragment key={log.log_id}>
                    <tr>
                      <td>{formatDate(log.created_at)}</td>
                      <td className="question-cell" title={log.question}>{log.question}</td>
                      <td>
                        <span className={`log-outcome ${log.outcome}`}>
                          {OUTCOME_LABELS[log.outcome] ?? log.outcome}
                        </span>
                      </td>
                      <td>{log.intent}</td>
                      <td>{formatMilliseconds(log.latency_ms)}</td>
                      <td className="mono">{log.total_tokens || "—"}</td>
                      <td>
                        {log.feedback > 0 ? (
                          <ThumbsUp size={14} className="feedback-up" />
                        ) : log.feedback < 0 ? (
                          <ThumbsDown size={14} className="feedback-down" />
                        ) : (
                          "—"
                        )}
                      </td>
                      <td>
                        <button
                          className="icon-button subtle"
                          type="button"
                          onClick={() => void toggleExpand(log.log_id)}
                          title={expandedId === log.log_id ? "收起执行轨迹" : "回放执行轨迹"}
                        >
                          <Workflow size={14} />
                        </button>
                      </td>
                    </tr>
                    {expandedId === log.log_id ? (
                      <tr className="log-detail-row">
                        <td colSpan={8}>
                          {expandedDetail === null ? (
                            <div className="empty-state"><Loader2 size={14} /> 正在载入轨迹...</div>
                          ) : (
                            <div className="log-replay">
                              {expandedDetail.answer_preview ? (
                                <p className="log-answer-preview">{expandedDetail.answer_preview}</p>
                              ) : null}
                              <ol className="trace-list">
                                {expandedDetail.trace.map((step: TraceStep, index: number) => (
                                  <li className="trace-item" key={`${step.name}-${index}`}>
                                    <div>
                                      <strong>{step.name}</strong>
                                      <span>{step.status}</span>
                                    </div>
                                    <p>{step.detail}</p>
                                  </li>
                                ))}
                              </ol>
                            </div>
                          )}
                        </td>
                      </tr>
                    ) : null}
                  </React.Fragment>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </section>
    </div>
  );
}
