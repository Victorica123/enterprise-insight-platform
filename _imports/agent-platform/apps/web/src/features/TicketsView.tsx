import React from "react";
import {
  CheckCircle2, ClipboardList, Loader2, ScrollText, ShieldQuestion, ThumbsDown, ThumbsUp, Ticket, Trash2,
} from "lucide-react";
import {
  type ActorRole, type TicketListResponse, getToolMetrics, listPendingActions, listToolCalls,
} from "../api";
import {
  MetricItem, formatDate, formatExpiry, formatMilliseconds, formatPercent,
} from "./common";
import "../styles/tickets.css";

export function TicketsView(props: {
  ticketList: TicketListResponse | null;
  pendingActions: Awaited<ReturnType<typeof listPendingActions>>;
  toolMetrics: Awaited<ReturnType<typeof getToolMetrics>> | null;
  toolCalls: Awaited<ReturnType<typeof listToolCalls>>;
  isLoadingTickets: boolean;
  approvingActionId: string | null;
  actorRole: ActorRole;
  handleDeleteTicket: (id: string) => void;
  handleApprove: (actionId: string, approved: boolean) => void;
  handleStatusDraft: (ticketId: string, newStatus: string) => void;
  statusTag: Record<string, string>;
  priorityTag: Record<string, string>;
  permissionHint?: string | null;
}) {
  const p = props;
  const [nextStatuses, setNextStatuses] = React.useState<Record<string, string>>({});
  return (
    <div className="tickets-container">
      {p.permissionHint ? (
        <div className="banner info-banner">
          <ShieldQuestion size={18} />
          <span>{p.permissionHint}</span>
        </div>
      ) : null}
      <section className="v3-metrics-band">
        <MetricItem label="工具调用" value={p.toolMetrics?.total_calls ?? 0} />
        <MetricItem label="执行成功率" value={formatPercent(p.toolMetrics?.success_rate)} />
        <MetricItem label="工具 P95" value={formatMilliseconds(p.toolMetrics?.p95_duration_ms)} />
        <MetricItem label="待审批" value={p.pendingActions.length} />
        <MetricItem label="重复执行违规" value={p.toolMetrics?.exact_once_violations ?? 0} />
      </section>

      {p.pendingActions.length > 0 ? (
        <section className="card pending-section">
          <h2>
            <ClipboardList size={19} />
            待审批操作（{p.pendingActions.length}）
          </h2>
          {p.pendingActions.map((action) => (
            <div className="pending-action-item" key={action.action_id}>
              <div className="pending-action-header">
                <span className="action-type-badge">{action.action_type === "create_ticket" ? "创建工单" : "更新状态"}</span>
                <span className="action-status pending">待审批 · {formatExpiry(action.expires_at)}</span>
              </div>
              <div className="pending-action-body">
                {action.action_type === "create_ticket" ? (
                  <>
                    <p><strong>标题：</strong>{String(action.payload.title ?? "")}</p>
                    <p><strong>优先级：</strong>{String(action.payload.priority ?? "")}</p>
                    <p><strong>描述：</strong>{String(action.payload.description ?? "").slice(0, 300)}</p>
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

      <section className="card">
        <h2>
          <Ticket size={19} />
          工单列表
          {p.ticketList ? <span className="count-badge">{p.ticketList.total}</span> : null}
          {p.isLoadingTickets ? <Loader2 size={16} className="spin" /> : null}
        </h2>
        {p.isLoadingTickets ? (
          <div className="empty-state">加载中...</div>
        ) : !p.ticketList || p.ticketList.tickets.length === 0 ? (
          <div className="empty-state">
            暂无工单。可在知识问答中让 AI 生成工单草稿。
          </div>
        ) : (
          <div className="ticket-table-wrapper">
            <table className="ticket-table">
              <thead>
                <tr>
                  <th>工单 ID</th>
                  <th>标题</th>
                  <th>状态</th>
                  <th>优先级</th>
                  <th>指派人</th>
                  <th>风险</th>
                  <th>创建时间</th>
                  <th>操作</th>
                </tr>
              </thead>
              <tbody>
                {p.ticketList.tickets.map((ticket) => (
                  <tr key={ticket.ticket_id}>
                    <td className="mono">{ticket.ticket_id.slice(0, 8)}</td>
                    <td>{ticket.title}</td>
                    <td>
                      <div className="status-editor">
                        <span className={"status-tag status-" + ticket.status}>{p.statusTag[ticket.status] ?? ticket.status}</span>
                        <select
                          value={nextStatuses[ticket.ticket_id] ?? ticket.status}
                          onChange={(event) => setNextStatuses((current) => ({
                            ...current,
                            [ticket.ticket_id]: event.target.value,
                          }))}
                          disabled={p.actorRole === "viewer"}
                          aria-label="目标状态"
                        >
                          {Object.entries(p.statusTag)
                            .filter(([status]) => ["open", "in_progress", "resolved", "closed"].includes(status))
                            .map(([status, label]) => <option key={status} value={status}>{label}</option>)}
                        </select>
                        <button
                          className="icon-button"
                          title="提交状态变更审批"
                          disabled={p.actorRole === "viewer" || (nextStatuses[ticket.ticket_id] ?? ticket.status) === ticket.status}
                          onClick={() => void p.handleStatusDraft(
                            ticket.ticket_id,
                            nextStatuses[ticket.ticket_id] ?? ticket.status,
                          )}
                        >
                          <CheckCircle2 size={14} />
                        </button>
                      </div>
                    </td>
                    <td><span className={"priority-tag priority-" + ticket.priority}>{p.priorityTag[ticket.priority] ?? ticket.priority}</span></td>
                    <td>{ticket.assignee || "-"}</td>
                    <td>{ticket.risk_level || "-"}</td>
                    <td>{formatDate(ticket.created_at)}</td>
                    <td>
                      <button
                        className="icon-button danger"
                        title="删除工单"
                        disabled={p.actorRole === "viewer"}
                        onClick={() => void p.handleDeleteTicket(ticket.ticket_id)}
                      >
                        <Trash2 size={14} />
                      </button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </section>

      <section className="audit-section">
        <h2><ScrollText size={19} />工具调用审计</h2>
        {p.toolCalls.length === 0 ? (
          <div className="empty-state">暂无工具调用记录。</div>
        ) : (
          <div className="ticket-table-wrapper">
            <table className="ticket-table audit-table">
              <thead><tr><th>工具</th><th>操作</th><th>状态</th><th>角色</th><th>耗时</th><th>时间</th></tr></thead>
              <tbody>
                {p.toolCalls.map((call) => (
                  <tr key={call.call_id}>
                    <td className="mono">{call.tool_name}</td>
                    <td>{call.operation}</td>
                    <td><span className={`audit-status audit-${call.status}`}>{call.status}</span></td>
                    <td>{call.actor_role}</td>
                    <td>{formatMilliseconds(call.duration_ms)}</td>
                    <td>{formatDate(call.created_at)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </section>
    </div>
  );
}
