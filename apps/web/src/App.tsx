import * as React from "react";
import { QueryClientProvider } from "@tanstack/react-query";
import { NavLink, Navigate, Route, Routes } from "react-router";
import { AlertCircle, Bot, BrainCircuit, ClipboardList, FileCheck2, LineChart, Loader2, LogOut, Network, Video, X } from "lucide-react";
import { AuthGate } from "./features/AuthGate";
import { ApiFailureDialog } from "./features/common";
import { WorkspaceSwitcher } from "./features/WorkspaceSwitcher";
import { EvidencePlayer, MediaWorkspace, type VideoEvidenceRequest } from "./features/MediaWorkspace";
import { useMediaWorkspace } from "./hooks/useMediaWorkspace";
import { useQAWorkspace } from "./hooks/useQAWorkspace";
import { useWorkspaceSession } from "./hooks/useWorkspaceSession";
import { createWorkspaceQueryClient, disposeWorkspaceQueries, workspaceIdentity } from "./queryClient";
import type { WorkspaceSession } from "./session";
import { WorkspaceContext } from "./workspaceContext";

const QAView = React.lazy(() => import("./features/QAView").then((module) => ({ default: module.QAView })));
const GraphView = React.lazy(() => import("./features/GraphView").then((module) => ({ default: module.GraphView })));
const MonitorView = React.lazy(() => import("./features/MonitorView").then((module) => ({ default: module.MonitorView })));
const AnalysisWorkspace = React.lazy(() => import("./features/AnalysisWorkspace").then((module) => ({ default: module.AnalysisWorkspace })));
const TicketsWorkspace = React.lazy(() => import("./features/TicketsWorkspace").then((module) => ({ default: module.TicketsWorkspace })));

export function App() {
  const auth = useWorkspaceSession();
  if (!auth.session) return <>
    {auth.error ? <div className="banner" role="alert">{auth.error}</div> : null}
    <AuthGate onAuthenticated={auth.acceptSession} />
  </>;
  return <WorkspaceScope key={workspaceIdentity(auth.session)} session={auth.session}
    onSwitched={auth.acceptSession} onLogout={auth.endSession} />;
}

type WorkspaceProps = {
  session: WorkspaceSession;
  onSwitched: (session: WorkspaceSession) => void;
  onLogout: () => Promise<void>;
};

function WorkspaceScope(props: WorkspaceProps) {
  const [client] = React.useState(createWorkspaceQueryClient);
  React.useEffect(() => () => { void disposeWorkspaceQueries(client); }, [client]);
  return <QueryClientProvider client={client}><WorkspaceContext.Provider value={props.session}>
    <WorkspaceApp {...props} />
  </WorkspaceContext.Provider></QueryClientProvider>;
}

function WorkspaceApp({ session, onSwitched, onLogout }: WorkspaceProps) {
  const [error, setError] = React.useState<string | null>(null);
  const [videoEvidence, setVideoEvidence] = React.useState<VideoEvidenceRequest | null>(null);
  const media = useMediaWorkspace(session, setError);
  const openEvidence = (assetId: string, startMs: number) => {
    const task = media.tasks.find((candidate) => candidate.videoId === assetId);
    if (!task) { setError("该视频证据不在当前工作区任务列表中，无法签发播放令牌。"); return; }
    setVideoEvidence({ taskId: task.taskId, fileName: task.fileName, startMs });
  };
  // The feature controller lives for the Workspace, so changing tabs preserves the conversation.
  const qa = useQAWorkspace(session, media.selectedAssetIds, setError, openEvidence);
  const navigation = [
    { path: "media", label: "视频证据", icon: Video, count: media.selectedAssetIds.length },
    { path: "qa", label: "知识问答", icon: Bot },
    { path: "analysis", label: "需求分析", icon: FileCheck2 },
    { path: "tickets", label: "工单管理", icon: ClipboardList, count: qa.tickets.pendingActions.length },
    { path: "graph", label: "关系图谱", icon: Network },
    { path: "monitor", label: "运行监控", icon: LineChart },
  ];
  return <main>
    <header>
      <div><h1><BrainCircuit size={28} />Enterprise Insight Platform</h1><p>视频与文档证据 · Agent 分析 · 业务行动闭环</p></div>
      <div className="role-controls">
        <WorkspaceSwitcher session={session} onSwitched={onSwitched} onError={setError} />
        <div className="role-control"><span>{session.username}</span><strong>{session.role}</strong></div>
        <button className="icon-button subtle" type="button" onClick={() => void onLogout()} title="退出登录"><LogOut size={16} /></button>
      </div>
    </header>
    {error ? <div className="banner" role="alert"><AlertCircle size={18} /><span>{error}</span>
      <button className="icon-button" type="button" onClick={() => setError(null)} aria-label="关闭"><X size={16} /></button>
    </div> : null}
    {qa.apiFailureNotice ? <ApiFailureDialog notice={qa.apiFailureNotice} onClose={qa.closeApiFailure} /> : null}
    <nav className="tab-nav" aria-label="工作区功能">
      {navigation.map(({ path, label, icon: Icon, count }) => <NavLink key={path} to={`/${path}`}
        className={({ isActive }) => `tab-button${isActive ? " active" : ""}`}>
        <Icon size={18} /><span>{label}</span>{count ? <span className="badge">{count}</span> : null}
      </NavLink>)}
    </nav>
    <React.Suspense fallback={<div className="card empty-state"><Loader2 className="spin" />正在加载…</div>}>
      <Routes>
        <Route path="/media" element={<MediaWorkspace session={session} tasks={media.tasks} runtime={media.runtime}
          loading={media.loading} selectedAssetIds={media.selectedAssetIds} onSelectionChange={media.setSelectedAssetIds}
          onRefresh={media.refresh} onError={setError} onPlay={setVideoEvidence} />} />
        <Route path="/qa" element={<QAView {...qa.props} />} />
        <Route path="/analysis" element={<AnalysisWorkspace selectedAssetIds={media.selectedAssetIds} onPlayEvidence={openEvidence} onError={setError} />} />
        <Route path="/tickets" element={<TicketsWorkspace controller={qa.tickets} actorRole={session.role} />} />
        <Route path="/graph" element={<GraphView actorRole={session.role} setError={setError} />} />
        <Route path="/monitor" element={<MonitorView embeddingStatus={qa.props.embeddingStatus} metricsSummary={qa.props.metricsSummary}
          onRefresh={qa.refreshWorkspace} actorRole={session.role} />} />
        <Route path="*" element={<Navigate to="/media" replace />} />
      </Routes>
    </React.Suspense>
    <EvidencePlayer request={videoEvidence} onClose={() => setVideoEvidence(null)} />
  </main>;
}
