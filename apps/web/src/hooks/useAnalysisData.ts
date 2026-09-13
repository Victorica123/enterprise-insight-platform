import * as React from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { getPublicationDeliverables, listAnalysisAudit, listAnalysisSessions, listPublicationQueue,
  type AnalysisSession, type PublicationDeliverables } from "../analysisApi";
import { useActiveWorkspace } from "../workspaceContext";
import { workspaceKey } from "../queryClient";
import { getErrorMessage } from "../features/common";

export function useAnalysisData(onError: (message: string) => void) {
  const viewer = useActiveWorkspace();
  const client = useQueryClient();
  const key = workspaceKey(viewer, "analysis");
  const [activeId, setActiveId] = React.useState<string | null>(null);
  const sessionsQuery = useQuery({ queryKey: [...key, "sessions"], queryFn: async ({ signal }) => {
    const [own, queue] = await Promise.all([listAnalysisSessions(signal), viewer.role === "viewer" ? [] : listPublicationQueue(signal)]);
    return [...own, ...queue.filter((candidate) => !own.some((item) => item.session_id === candidate.session_id))];
  } });
  const sessions = sessionsQuery.data ?? [];
  const active = sessions.find((item) => item.session_id === activeId) ?? sessions[0] ?? null;
  const auditKey = [...key, "audit", active?.session_id, active?.checkpoint_version, active?.status];
  const auditQuery = useQuery({ queryKey: auditKey, enabled: Boolean(active && active.owner_id === viewer.userId),
    queryFn: ({ signal }) => listAnalysisAudit(active!.session_id, signal) });
  const deliverablesKey = [...key, "deliverables", active?.session_id];
  const deliverablesQuery = useQuery({ queryKey: deliverablesKey, enabled: active?.status === "PUBLISHED",
    queryFn: ({ signal }) => getPublicationDeliverables(active!.session_id, signal) });
  const error = sessionsQuery.error ?? auditQuery.error ?? deliverablesQuery.error;
  React.useEffect(() => { if (error) onError(getErrorMessage(error)); }, [error, onError]);
  const setSessions: React.Dispatch<React.SetStateAction<AnalysisSession[]>> = (next) => {
    client.setQueryData<AnalysisSession[]>([...key, "sessions"], (current) => typeof next === "function" ? next(current ?? []) : next);
  };
  const setDeliverables: React.Dispatch<React.SetStateAction<PublicationDeliverables | null>> = (next) => {
    client.setQueryData<PublicationDeliverables | null>(deliverablesKey, (current) => typeof next === "function" ? next(current ?? null) : next);
  };
  return {
    viewer, sessions, active, setSessions, setActive: (value: AnalysisSession | null) => setActiveId(value?.session_id ?? null),
    audit: auditQuery.data ?? [], deliverables: deliverablesQuery.data ?? null, setDeliverables,
    refreshAudit: () => client.invalidateQueries({ queryKey: [...key, "audit"] }),
    refreshRelated: () => Promise.all(["knowledge", "graph", "tickets"].map((domain) =>
      client.invalidateQueries({ queryKey: workspaceKey(viewer, domain) }))),
    refreshDeliverables: async () => { await client.invalidateQueries({ queryKey: deliverablesKey }); },
  };
}
