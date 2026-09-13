import * as React from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { approveAction, createStatusDraft, deleteTicket, listPendingActions, listTickets } from "../ticketApi";
import { getToolMetrics, listToolCalls } from "../observabilityApi";
import { isPermissionError } from "../apiClient";
import { getErrorMessage } from "../features/common";
import type { WorkspaceSession } from "../session";
import { workspaceKey } from "../queryClient";

export function useTicketsWorkspace(session: WorkspaceSession, onError: (message: string) => void) {
  const client = useQueryClient();
  const key = workspaceKey(session, "tickets");
  const writer = session.role !== "viewer";
  const tickets = useQuery({ queryKey: [...key, "list"], queryFn: ({ signal }) => listTickets(undefined, signal) });
  const actions = useQuery({ queryKey: [...key, "pending"], enabled: writer,
    queryFn: ({ signal }) => listPendingActions("pending", session.role, signal) });
  const metrics = useQuery({ queryKey: [...key, "metrics"], enabled: writer, queryFn: ({ signal }) => getToolMetrics(signal) });
  const calls = useQuery({ queryKey: [...key, "calls"], enabled: writer,
    queryFn: ({ signal }) => listToolCalls(20, session.role, signal) });
  const refreshTickets = async () => { await client.invalidateQueries({ queryKey: key }); };
  const error = tickets.error ?? actions.error ?? metrics.error ?? calls.error;
  React.useEffect(() => { if (error && !isPermissionError(error)) onError(getErrorMessage(error)); }, [error, onError]);
  const approval = useMutation({
    mutationFn: ({ actionId, approved }: { actionId: string; approved: boolean }) => approveAction(actionId, approved, session.role, session.userId),
    onSuccess: refreshTickets, onError: (caught) => onError(getErrorMessage(caught)),
  });
  const deletion = useMutation({ mutationFn: (id: string) => deleteTicket(id, session.role),
    onSuccess: refreshTickets, onError: (caught) => onError(getErrorMessage(caught)) });
  const status = useMutation({ mutationFn: ({ id, value }: { id: string; value: string }) => createStatusDraft(id, value, session.role, session.userId),
    onSuccess: refreshTickets, onError: (caught) => onError(getErrorMessage(caught)) });
  return {
    ticketList: tickets.data ?? null, pendingActions: actions.data ?? [], toolMetrics: metrics.data ?? null,
    toolCalls: calls.data ?? [], isLoadingTickets: tickets.isPending,
    ticketsPermissionHint: !writer || isPermissionError(error) ? "当前工作区角色仅可查看工单，审批与审计需要成员或管理员权限。" : null,
    approvingActionId: approval.isPending ? approval.variables.actionId : null,
    refreshTickets,
    handleApprove: (actionId: string, approved: boolean) => approval.mutate({ actionId, approved }),
    handleDeleteTicket: (id: string) => { if (window.confirm("确定删除这个工单吗？")) deletion.mutate(id); },
    handleStatusDraft: (id: string, value: string) => status.mutate({ id, value }),
  };
}
