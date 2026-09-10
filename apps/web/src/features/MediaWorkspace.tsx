import React from "react";
import {
  CheckCircle2, Clock3, FileVideo2, Loader2, Play, RefreshCw, RotateCcw,
  Trash2, Upload, Video,
} from "lucide-react";
import {
  type MediaRuntime, type MediaTask, createPlayback, deleteMediaTask, retryMediaTask, uploadVideo,
} from "../mediaApi";
import { formatDate, getErrorMessage } from "./common";
import "../styles/media.css";

export type VideoEvidenceRequest = { taskId: string; fileName: string; startMs: number };

export function MediaWorkspace(props: {
  tasks: MediaTask[];
  runtime: MediaRuntime | null;
  loading: boolean;
  selectedAssetIds: string[];
  onSelectionChange: (ids: string[]) => void;
  onRefresh: () => Promise<void>;
  onError: (message: string) => void;
  onPlay: (request: VideoEvidenceRequest) => void;
}) {
  const [file, setFile] = React.useState<File | null>(null);
  const [busy, setBusy] = React.useState(false);

  async function upload(event: React.FormEvent) {
    event.preventDefault();
    if (!file) return;
    setBusy(true);
    try {
      await uploadVideo(file);
      setFile(null);
      await props.onRefresh();
    } catch (caught) {
      props.onError(getErrorMessage(caught));
    } finally {
      setBusy(false);
    }
  }

  async function mutate(task: MediaTask, action: "retry" | "delete") {
    if (action === "delete" && !window.confirm(`删除视频任务「${task.fileName}」？`)) return;
    try {
      if (action === "retry") await retryMediaTask(task.taskId);
      else await deleteMediaTask(task.taskId);
      await props.onRefresh();
    } catch (caught) {
      props.onError(getErrorMessage(caught));
    }
  }

  function toggle(assetId: string) {
    props.onSelectionChange(props.selectedAssetIds.includes(assetId)
      ? props.selectedAssetIds.filter((id) => id !== assetId)
      : [...props.selectedAssetIds, assetId]);
  }

  return (
    <div className="media-workspace">
      <section className="card media-hero">
        <div><span className="eyebrow">MEDIA → EVIDENCE → AGENT</span><h2><Video size={22} />视频证据工作台</h2>
          <p>上传后自动转写、摘要并同步为可检索的时间戳证据。勾选视频即可限定 Agent 的分析范围。</p>
          {props.runtime ? <div className={`media-runtime ${props.runtime.transcriptMode === "mock" ? "mock" : "real"}`}>
            <strong>{props.runtime.transcriptMode === "mock" ? "当前为验证模式" : "当前为真实处理模式"}</strong>
            <span>转写：{props.runtime.transcriptMode === "mock" ? "模拟" : "Whisper API"}</span>
            <span>摘要：{props.runtime.summaryMode === "mock" ? "本地模拟" : "外部 LLM"}</span>
            <span>调度：{props.runtime.dispatchMode}</span>
            <span>存储：{props.runtime.storageType}</span>
            <span>身份：{props.runtime.oidcEnabled ? `OIDC + ${props.runtime.jwtAlgorithm}` : props.runtime.jwtAlgorithm}</span>
            <span>模型出境：{props.runtime.modelEgressAllowed ? "本工作区已批准" : "未批准（仅本地）"}</span>
            {props.runtime.retentionEnabled ? <span>保留期：媒体 {props.runtime.mediaRetentionDays} 天 / 转写 {props.runtime.transcriptRetentionDays} 天 / 审计 {props.runtime.auditRetentionDays} 天</span> : null}
          </div> : null}
        </div>
        <form onSubmit={upload} className="video-upload">
          <input type="file" accept="video/*,.mp4,.mov,.mkv,.webm" onChange={(event) => setFile(event.target.files?.[0] ?? null)} />
          <button className="button" disabled={!file || busy}>{busy ? <Loader2 size={15} className="spin" /> : <Upload size={15} />}{busy ? "上传中" : "上传视频"}</button>
        </form>
      </section>
      <section className="media-toolbar">
        <div><strong>{props.tasks.length}</strong> 个视频 · <strong>{props.selectedAssetIds.length}</strong> 个已纳入分析</div>
        <button className="icon-button subtle" onClick={() => void props.onRefresh()} title="刷新"><RefreshCw size={16} /></button>
      </section>
      {props.loading ? <div className="card empty-state"><Loader2 size={18} className="spin" /> 正在加载视频任务…</div>
        : props.tasks.length === 0 ? <div className="card empty-state"><FileVideo2 size={30} /><p>还没有视频。上传一个视频，完整链路会在本机自动运行。</p></div>
        : <div className="media-grid">{props.tasks.map((task) => {
          const selected = props.selectedAssetIds.includes(task.videoId);
          const selectionLabel = selected ? "移出 Agent 分析范围" : "纳入 Agent 分析范围";
          return <article className={`card media-task ${selected ? "selected" : ""}`} key={task.taskId}>
            <div className="media-task-head">
              <button
                className={`asset-check ${selected ? "active" : ""}`}
                onClick={() => toggle(task.videoId)}
                title={selectionLabel}
                aria-label={selectionLabel}
                aria-pressed={selected}
              >
                <CheckCircle2 size={18} />
              </button>
              <div><strong>{task.fileName}</strong><span>{formatDate(task.createdAt)}</span></div>
              <span className={`task-status status-${task.status.toLowerCase()}`}>{statusLabel(task.status)}</span>
            </div>
            <p className="media-summary">{task.summary || task.errorMessage || "正在生成转写与摘要…"}</p>
            <div className="media-meta"><span><Clock3 size={14} />{formatDuration(task.transcriptDurationMs)}</span><span>v{task.transcriptVersion}</span><span>{task.transcriptSegments.length} 段证据</span></div>
            <div className="media-actions">
              <button className="button secondary" disabled={task.status !== "COMPLETED" || !task.mediaRetained} onClick={() => props.onPlay({ taskId: task.taskId, fileName: task.fileName, startMs: 0 })}><Play size={14} />{task.mediaRetained ? "播放" : "媒体已过保留期"}</button>
              {task.status === "FAILED" ? <button className="icon-button subtle" onClick={() => void mutate(task, "retry")} title="重试"><RotateCcw size={15} /></button> : null}
              <button className="icon-button danger" onClick={() => void mutate(task, "delete")} title="删除"><Trash2 size={15} /></button>
            </div>
          </article>;
        })}</div>}
    </div>
  );
}

export function EvidencePlayer({ request, onClose }: { request: VideoEvidenceRequest | null; onClose: () => void }) {
  const videoRef = React.useRef<HTMLVideoElement | null>(null);
  const [url, setUrl] = React.useState<string | null>(null);
  const [error, setError] = React.useState<string | null>(null);
  React.useEffect(() => {
    setUrl(null); setError(null);
    if (!request) return;
    void createPlayback(request.taskId).then((playback) => setUrl(playback.url)).catch((caught) => setError(getErrorMessage(caught)));
  }, [request]);
  if (!request) return null;
  return <div className="player-backdrop" role="dialog" aria-modal="true" onClick={onClose}>
    <section className="player-dialog" onClick={(event) => event.stopPropagation()}>
      <header><div><strong>{request.fileName}</strong><span>定位至 {formatTimestamp(request.startMs)}</span></div><button className="icon-button" onClick={onClose}>×</button></header>
      {error ? <div className="auth-error">{error}</div> : url ? <video ref={videoRef} controls autoPlay src={url} onLoadedMetadata={() => { if (videoRef.current) videoRef.current.currentTime = request.startMs / 1000; }} /> : <div className="empty-state"><Loader2 className="spin" />正在签发本地播放令牌…</div>}
    </section>
  </div>;
}

export function formatTimestamp(ms: number): string {
  const seconds = Math.floor(ms / 1000);
  return `${Math.floor(seconds / 60)}:${String(seconds % 60).padStart(2, "0")}`;
}

function formatDuration(ms: number | null): string { return ms == null ? "--:--" : formatTimestamp(ms); }
function statusLabel(status: MediaTask["status"]): string {
  return { QUEUED: "排队中", TRANSCRIBING: "转写中", SUMMARIZING: "摘要中", COMPLETED: "证据就绪", FAILED: "失败" }[status];
}
