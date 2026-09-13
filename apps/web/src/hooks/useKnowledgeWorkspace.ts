import * as React from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { getEmbeddingStatus, getSystemStatus, listDocuments } from "../knowledgeApi";
import { getMetricsSummary } from "../observabilityApi";
import type { EmbeddingStatus, SystemStatus } from "../api";
import type { WorkspaceSession } from "../session";
import { workspaceKey } from "../queryClient";
import { getErrorMessage } from "../features/common";

export function useKnowledgeWorkspace(session: WorkspaceSession, onError: (message: string) => void) {
  const client = useQueryClient();
  const key = workspaceKey(session, "knowledge");
  const documents = useQuery({ queryKey: [...key, "documents"], queryFn: ({ signal }) => listDocuments(signal) });
  const embedding = useQuery({ queryKey: [...key, "embedding"], queryFn: ({ signal }) => getEmbeddingStatus(signal) });
  const system = useQuery({ queryKey: [...key, "system"], queryFn: ({ signal }) => getSystemStatus(signal) });
  const metrics = useQuery({ queryKey: [...key, "metrics"], queryFn: ({ signal }) => getMetricsSummary(signal) });
  const error = documents.error ?? embedding.error ?? system.error ?? metrics.error;
  React.useEffect(() => { if (error) onError(getErrorMessage(error)); }, [error, onError]);
  return {
    documents: documents.data ?? [], embeddingStatus: embedding.data ?? null,
    systemStatus: system.data ?? null, metricsSummary: metrics.data ?? null,
    isLoadingDocuments: documents.isPending,
    refreshWorkspace: async () => { await client.invalidateQueries({ queryKey: key }); },
    setEmbeddingStatus: (value: EmbeddingStatus) => client.setQueryData([...key, "embedding"], value),
    setSystemStatus: (updater: (value: SystemStatus | null) => SystemStatus | null) =>
      client.setQueryData<SystemStatus | null>([...key, "system"], (value) => updater(value ?? null)),
  };
}
