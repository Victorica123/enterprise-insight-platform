import * as React from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { getMediaRuntime, listMediaTasks, type MediaTask } from "../mediaApi";
import type { WorkspaceSession } from "../session";
import { getErrorMessage } from "../features/common";
import { mediaPollDelay, workspaceIdentity } from "../queryClient";

const EMPTY_TASKS: MediaTask[] = [];

export function useMediaWorkspace(session: WorkspaceSession, onError: (message: string) => void) {
  const client = useQueryClient();
  const identity = workspaceIdentity(session);
  const key = ["workspace", identity, "media"];
  const [selectedAssetIds, setSelectedAssetIds] = React.useState<string[]>([]);
  const tasksQuery = useQuery({ queryKey: [...key, "tasks"], queryFn: ({ signal }) => listMediaTasks(signal),
    refetchInterval: (query) => mediaPollDelay(query.state.data, query.state.error,
      query.state.fetchFailureCount || query.state.errorUpdateCount), refetchIntervalInBackground: false });
  const runtimeQuery = useQuery({ queryKey: [...key, "runtime"], queryFn: ({ signal }) => getMediaRuntime(signal), staleTime: 60_000 });
  const tasks = tasksQuery.data ?? EMPTY_TASKS;
  const error = tasksQuery.error ?? runtimeQuery.error;
  React.useEffect(() => { if (error) onError(getErrorMessage(error)); }, [error, onError]);
  React.useEffect(() => {
    setSelectedAssetIds((current) => {
      const next = current.filter((id) => tasks.some((task) => task.videoId === id));
      return next.length === current.length ? current : next;
    });
  }, [tasks]);
  const refresh = React.useCallback(async () => {
    await client.invalidateQueries({ queryKey: ["workspace", identity, "media"] });
  }, [client, identity]);
  return { tasks, runtime: runtimeQuery.data ?? null, loading: tasksQuery.isPending,
    selectedAssetIds, setSelectedAssetIds, refresh };
}
