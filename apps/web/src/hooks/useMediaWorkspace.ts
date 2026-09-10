import React from "react";
import { getMediaRuntime, listMediaTasks, type MediaRuntime, type MediaTask } from "../mediaApi";
import type { WorkspaceSession } from "../session";
import { getErrorMessage } from "../features/common";

export function useMediaWorkspace(
  session: WorkspaceSession | null,
  onError: (message: string) => void,
) {
  const [tasks, setTasks] = React.useState<MediaTask[]>([]);
  const [runtime, setRuntime] = React.useState<MediaRuntime | null>(null);
  const [loading, setLoading] = React.useState(false);
  const [selectedAssetIds, setSelectedAssetIds] = React.useState<string[]>([]);

  const refresh = React.useCallback(async () => {
    if (!session) return;
    setLoading(true);
    try {
      const [next, nextRuntime] = await Promise.all([listMediaTasks(), getMediaRuntime()]);
      setTasks(next);
      setRuntime(nextRuntime);
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
      setRuntime(null);
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

  return { tasks, runtime, loading, selectedAssetIds, setSelectedAssetIds, refresh };
}
