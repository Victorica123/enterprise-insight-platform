import React from "react";
import { listMediaTasks, type MediaTask } from "../mediaApi";
import type { WorkspaceSession } from "../session";
import { getErrorMessage } from "../features/common";

export function useMediaWorkspace(
  session: WorkspaceSession | null,
  onError: (message: string) => void,
) {
  const [tasks, setTasks] = React.useState<MediaTask[]>([]);
  const [loading, setLoading] = React.useState(false);
  const [selectedAssetIds, setSelectedAssetIds] = React.useState<string[]>([]);

  const refresh = React.useCallback(async () => {
    if (!session) return;
    setLoading(true);
    try {
      const next = await listMediaTasks();
      setTasks(next);
      setSelectedAssetIds((current) => current.filter(
        (assetId) => next.some((task) => task.videoId === assetId),
      ));
    } catch (caught) {
      onError(getErrorMessage(caught));
    } finally {
      setLoading(false);
    }
  }, [session, onError]);

  React.useEffect(() => {
    if (!session) {
      setTasks([]);
      setSelectedAssetIds([]);
      return;
    }
    void refresh();
  }, [session, refresh]);

  React.useEffect(() => {
    if (!session || !tasks.some((task) => !["COMPLETED", "FAILED"].includes(task.status))) return;
    const timer = window.setInterval(() => void refresh(), 2000);
    return () => window.clearInterval(timer);
  }, [session, tasks, refresh]);

  return { tasks, loading, selectedAssetIds, setSelectedAssetIds, refresh };
}
