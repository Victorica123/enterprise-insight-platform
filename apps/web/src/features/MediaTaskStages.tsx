import * as React from "react";
import { useInfiniteQuery } from "@tanstack/react-query";
import { listMediaTaskStages, type MediaTask, type MediaTaskStage } from "../mediaApi";
import { mediaPollDelay, workspaceKey } from "../queryClient";
import type { WorkspaceSession } from "../session";
import { getErrorMessage, formatDate } from "./common";

const stages: Record<MediaTaskStage["stage"], string> = {
  STORAGE_RESOLVE: "读取媒体", AUDIO_EXTRACTION: "抽取音频", TRANSCRIPTION: "转写",
  SUMMARY: "摘要", RESULT_REUSE: "复用已有结果", RESULT_COMMIT: "保存结果", DELIVERY: "同步知识库",
};
const statuses = { RUNNING: "进行中", SUCCEEDED: "完成", FAILED: "失败", ABANDONED: "已中断" };
const errors: Record<NonNullable<MediaTaskStage["errorCode"]>, string> = {
  STAGE_FAILED: "处理失败", LEASE_RECOVERED: "任务已由新执行接管", DELIVERY_REJECTED: "知识库拒绝接收",
  DELIVERY_RETRY: "同步失败，等待重试", LEASE_LOST: "执行权已变更",
};

export function MediaTaskStages(props: { task: MediaTask; session: WorkspaceSession }) {
  const [open, setOpen] = React.useState(false);
  return <details className="media-stages" onToggle={(event) => setOpen(event.currentTarget.open)}>
    <summary>处理记录</summary>{open ? <StageTimeline {...props} /> : null}
  </details>;
}

function StageTimeline({ task, session }: { task: MediaTask; session: WorkspaceSession }) {
  const query = useInfiniteQuery({
    queryKey: [...workspaceKey(session, "media"), "stages", task.taskId], initialPageParam: 0,
    queryFn: ({ pageParam, signal }) => listMediaTaskStages(task.taskId, pageParam, signal),
    getNextPageParam: (last) => last.hasMore ? last.nextCursor : undefined,
    refetchInterval: (state) => {
      if (state.state.error) return mediaPollDelay(undefined, state.state.error, state.state.errorUpdateCount);
      const running = state.state.data?.pages.some((page) => page.items.some((item) => item.status === "RUNNING"));
      return mediaPollDelay([task], null, 0) || (running || Date.now() - Date.parse(task.updatedAt) < 60_000 ? 5000 : false);
    },
    refetchIntervalInBackground: false,
  });
  const items = query.data?.pages.flatMap((page) => page.items) ?? [];
  return <div>
    {query.error ? <p role="alert">{getErrorMessage(query.error)}</p> : null}
    {query.isPending ? <p>正在读取处理记录…</p> : !items.length ? <p>暂无处理记录；早期任务不会补造历史步骤。</p> : null}
    <ol>{items.map((item) => <li key={item.id}>
      <div><strong>{stages[item.stage]}</strong><span className={`stage-outcome stage-${item.status.toLowerCase()}`}>{statuses[item.status]}</span></div>
      <small>{formatDate(item.startedAt)}{item.durationMs != null ? ` · ${item.durationMs} ms` : ""}</small>
      {item.errorCode ? <p>{errors[item.errorCode]}</p> : null}
    </li>)}</ol>
    <div className="media-actions">
      <button className="button secondary" disabled={query.isFetching} onClick={() => void query.refetch()}>刷新记录</button>
      {query.hasNextPage ? <button className="button secondary" disabled={query.isFetching} onClick={() => void query.fetchNextPage()}>更多记录</button> : null}
    </div>
  </div>;
}
