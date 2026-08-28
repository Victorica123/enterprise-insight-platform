import React from "react";
import { createRoot } from "react-dom/client";
import {
  AlertCircle, Bot, BrainCircuit, ClipboardList, LineChart, Network, ShieldCheck, UserCircle2, X,
} from "lucide-react";

import {
  approveAction,
  askQuestion,
  isPermissionError,
  type ActorRole,
  type AnswerMode,
  type ChatMetricsSummary,
  type ChatResponse,
  type EmbeddingStatus,
  type RetrieverMode,
  type SystemStatus,
  type TicketListResponse,
  type WorkflowMode,
  createStatusDraft,
  deleteDocument,
  deleteTicket,
  getEmbeddingStatus,
  getMetricsSummary,
  getSystemStatus,
  getToolMetrics,
  listDocuments,
  listPendingActions,
  listTickets,
  listToolCalls,
  rebuildEmbeddings,
  submitFeedback,
  uploadDocument,
} from "./api";
import { GraphView } from "./features/GraphView";
import { MonitorView } from "./features/MonitorView";
import { QAView } from "./features/QAView";
import { TicketsView } from "./features/TicketsView";
import {
  ApiFailureDialog,
  type ApiFailureNotice,
  getApiFailureReason,
  getErrorMessage,
} from "./features/common";
import "./styles/base.css";

function App() {
  const fileInputRef = React.useRef<HTMLInputElement | null>(null);
  const [documents, setDocuments] = React.useState<Awaited<ReturnType<typeof listDocuments>>>([]);
  const [selectedFile, setSelectedFile] = React.useState<File | null>(null);
  const [question, setQuestion] = React.useState("客户 A 的项目为什么延期？");
  const [answerMode, setAnswerMode] = React.useState<AnswerMode>("auto");
  const [retrieverMode, setRetrieverMode] = React.useState<RetrieverMode>("keyword");
  const [workflowMode, setWorkflowMode] = React.useState<WorkflowMode>("agentic");
  const [actorRole, setActorRole] = React.useState<ActorRole>("operator");
  // 职责分离演示用身份标识：匿名时不启用"发起人不能自批"；换不同 ID 可演示四眼审批
  const [actorUser, setActorUser] = React.useState<string>(
    () => window.localStorage.getItem("ea.actorUser") ?? "anonymous",
  );
  React.useEffect(() => {
    window.localStorage.setItem("ea.actorUser", actorUser);
  }, [actorUser]);
  const [embeddingStatus, setEmbeddingStatus] = React.useState<EmbeddingStatus | null>(null);
  const [systemStatus, setSystemStatus] = React.useState<SystemStatus | null>(null);
  const [metricsSummary, setMetricsSummary] = React.useState<ChatMetricsSummary | null>(null);
  const [chatResponse, setChatResponse] = React.useState<ChatResponse | null>(null);
  const [isLoadingDocuments, setIsLoadingDocuments] = React.useState(false);
  const [isUploading, setIsUploading] = React.useState(false);
  const [isAsking, setIsAsking] = React.useState(false);
  const [isRebuildingEmbeddings, setIsRebuildingEmbeddings] = React.useState(false);
  const [deletingDocumentId, setDeletingDocumentId] = React.useState<string | null>(null);
  const [error, setError] = React.useState<string | null>(null);
  const [apiFailureNotice, setApiFailureNotice] = React.useState<ApiFailureNotice | null>(null);

  // V3: ticket & approval state
  // hash 深链路由：#/qa #/tickets #/graph #/monitor 可直达对应面板（支持回退/分享链接）
  const readTabFromHash = (): "qa" | "tickets" | "graph" | "monitor" => {
    const tab = window.location.hash.replace(/^#\/?/, "");
    return (["qa", "tickets", "graph", "monitor"] as const).includes(tab as never)
      ? (tab as "qa" | "tickets" | "graph" | "monitor")
      : "qa";
  };
  const [activeTab, setActiveTab] = React.useState<"qa" | "tickets" | "graph" | "monitor">(readTabFromHash);
  const switchTab = React.useCallback((tab: "qa" | "tickets" | "graph" | "monitor") => {
    window.location.hash = `/${tab}`;
    setActiveTab(tab);
  }, []);
  React.useEffect(() => {
    const onHashChange = () => setActiveTab(readTabFromHash());
    window.addEventListener("hashchange", onHashChange);
    return () => window.removeEventListener("hashchange", onHashChange);
  }, []);
  const [ticketList, setTicketList] = React.useState<TicketListResponse | null>(null);
  const [pendingActions, setPendingActions] = React.useState<Awaited<ReturnType<typeof listPendingActions>>>([]);
  const [toolMetrics, setToolMetrics] = React.useState<Awaited<ReturnType<typeof getToolMetrics>> | null>(null);
  const [toolCalls, setToolCalls] = React.useState<Awaited<ReturnType<typeof listToolCalls>>>([]);
  const [isLoadingTickets, setIsLoadingTickets] = React.useState(false);
  const [ticketsPermissionHint, setTicketsPermissionHint] = React.useState<string | null>(null);
  const [approvingActionId, setApprovingActionId] = React.useState<string | null>(null);
  // V5: answer feedback state
  const [answerFeedback, setAnswerFeedback] = React.useState<"up" | "down" | null>(null);
  const [isSendingFeedback, setIsSendingFeedback] = React.useState(false);

  const refreshWorkspace = React.useCallback(async () => {
    setIsLoadingDocuments(true);
    setError(null);
    try {
      const [nextDocuments, nextEmbeddingStatus, nextSystemStatus, nextMetricsSummary] = await Promise.all([
        listDocuments(),
        getEmbeddingStatus(),
        getSystemStatus(),
        getMetricsSummary(),
      ]);
      setDocuments(nextDocuments);
      setEmbeddingStatus(nextEmbeddingStatus);
      setSystemStatus(nextSystemStatus);
      setMetricsSummary(nextMetricsSummary);
    } catch (caught) {
      setError(getErrorMessage(caught));
    } finally {
      setIsLoadingDocuments(false);
    }
  }, []);

  const refreshTickets = React.useCallback(async () => {
    setIsLoadingTickets(true);
    try {
      const [tickets, actions, metrics, calls] = await Promise.all([
        listTickets(),
        listPendingActions("pending", actorRole),
        getToolMetrics(),
        listToolCalls(20, actorRole),
      ]);
      setTicketList(tickets);
      setPendingActions(actions);
      setToolMetrics(metrics);
      setToolCalls(calls);
      setTicketsPermissionHint(null);
    } catch (caught) {
      // viewer 角色无法读取审批/审计数据时给出切换提示，其余错误静默（服务可能未启动）
      setTicketsPermissionHint(
        isPermissionError(caught) ? "当前角色（viewer）无权查看待审批与审计数据，请在右上角切换为 operator 或 admin。" : null,
      );
    } finally {
      setIsLoadingTickets(false);
    }
  }, [actorRole]);

  React.useEffect(() => {
    void refreshWorkspace();
    void refreshTickets();
  }, [refreshWorkspace, refreshTickets]);

  async function handleUpload(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!selectedFile) {
      setError("请选择一个 .txt、.md 或 .pdf 文件。");
      return;
    }
    setIsUploading(true);
    setError(null);
    try {
      await uploadDocument(selectedFile, actorRole);
      setSelectedFile(null);
      if (fileInputRef.current) {
        fileInputRef.current.value = "";
      }
      await refreshWorkspace();
    } catch (caught) {
      setError(getErrorMessage(caught));
    } finally {
      setIsUploading(false);
    }
  }

  async function handleAsk(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!question.trim()) {
      setError("请输入问题。");
      return;
    }
    setIsAsking(true);
    setError(null);
    setApiFailureNotice(null);
    setAnswerFeedback(null);
    try {
      const response = await askQuestion(question.trim(), answerMode, retrieverMode, workflowMode, actorRole, actorUser);
      setChatResponse(response);
      const failedApiStep = response.trace.find(
        (step) => step.name === "answer" && ["api_failed", "local_fallback"].includes(step.status),
      );
      if (failedApiStep) {
        setApiFailureNotice({
          reason: getApiFailureReason(failedApiStep.detail),
          requestedMode: answerMode,
        });
      }
      void getMetricsSummary().then(setMetricsSummary).catch(() => undefined);
      void refreshTickets();
    } catch (caught) {
      setError(getErrorMessage(caught));
    } finally {
      setIsAsking(false);
    }
  }

  async function handleDeleteDocument(documentId: string) {
    const target = documents.find((document) => document.document_id === documentId);
    const confirmed = window.confirm("确定删除文档「" + (target?.filename ?? documentId) + "」吗？");
    if (!confirmed) return;
    setDeletingDocumentId(documentId);
    setError(null);
    try {
      await deleteDocument(documentId, actorRole);
      if (chatResponse?.sources.some((source) => source.document_id === documentId)) {
        setChatResponse(null);
      }
      await refreshWorkspace();
    } catch (caught) {
      setError(getErrorMessage(caught));
    } finally {
      setDeletingDocumentId(null);
    }
  }

  async function handleRebuildEmbeddings() {
    setIsRebuildingEmbeddings(true);
    setError(null);
    try {
      const result = await rebuildEmbeddings(actorRole);
      setEmbeddingStatus(result);
      setSystemStatus((current) => (current ? { ...current, embedding: result, chunk_count: result.total_chunks } : null));
    } catch (caught) {
      setError(getErrorMessage(caught));
    } finally {
      setIsRebuildingEmbeddings(false);
    }
  }

  async function handleCopyAnswer() {
    if (!chatResponse?.answer) return;
    try {
      await navigator.clipboard.writeText(chatResponse.answer);
    } catch {
      const textarea = document.createElement("textarea");
      textarea.value = chatResponse.answer;
      document.body.appendChild(textarea);
      textarea.select();
      document.execCommand("copy");
      document.body.removeChild(textarea);
    }
  }

  async function handleApprove(actionId: string, approved: boolean) {
    setApprovingActionId(actionId);
    setError(null);
    try {
      await approveAction(actionId, approved, actorRole, actorUser);
      await refreshTickets();
    } catch (caught) {
      setError(getErrorMessage(caught));
    } finally {
      setApprovingActionId(null);
    }
  }

  async function handleAnswerFeedback(rating: "up" | "down") {
    if (!chatResponse?.log_id || answerFeedback) return;
    setIsSendingFeedback(true);
    setError(null);
    try {
      await submitFeedback(chatResponse.log_id, rating);
      setAnswerFeedback(rating);
    } catch (caught) {
      setError(getErrorMessage(caught));
    } finally {
      setIsSendingFeedback(false);
    }
  }

  async function handleDeleteTicket(ticketId: string) {
    const confirmed = window.confirm("确定删除这个工单吗？");
    if (!confirmed) return;
    try {
      await deleteTicket(ticketId, actorRole);
      await refreshTickets();
    } catch (caught) {
      setError(getErrorMessage(caught));
    }
  }

  async function handleStatusDraft(ticketId: string, newStatus: string) {
    setError(null);
    try {
      await createStatusDraft(ticketId, newStatus, actorRole, actorUser);
      await refreshTickets();
    } catch (caught) {
      setError(getErrorMessage(caught));
    }
  }

  const statusTag: Record<string, string> = {
    draft: "草稿", pending: "待处理", open: "打开",
    in_progress: "处理中", resolved: "已解决", closed: "已关闭",
  };
  const priorityTag: Record<string, string> = {
    low: "低", medium: "中", high: "高", critical: "紧急",
  };

  return (
    <main>
      <header>
        <div>
          <h1>
            <BrainCircuit size={28} />
            Enterprise AI Workflow Assistant
          </h1>
          <p>V5 · 知识问答 + 工单审批 + 关系图谱 + 运行监控</p>
        </div>
        <div className="role-controls">
          <label className="role-control" title="用户标识：职责分离时发起人不能自批，换 ID 可演示四眼审批">
            <UserCircle2 size={16} />
            <span>用户</span>
            <input
              value={actorUser}
              onChange={(event) => setActorUser(event.target.value.trim().toLowerCase() || "anonymous")}
              size={8}
              aria-label="用户标识"
            />
          </label>
          <label className="role-control">
            <ShieldCheck size={16} />
            <span>演示角色</span>
            <select value={actorRole} onChange={(event) => setActorRole(event.target.value as ActorRole)}>
              <option value="viewer">viewer</option>
              <option value="operator">operator</option>
              <option value="admin">admin</option>
            </select>
          </label>
        </div>
      </header>

      {error ? (
        <div className="banner">
          <AlertCircle size={18} />
          <span>{error}</span>
          <button className="icon-button" type="button" onClick={() => setError(null)} aria-label="关闭">
            <X size={16} />
          </button>
        </div>
      ) : null}

      {apiFailureNotice ? (
        <ApiFailureDialog notice={apiFailureNotice} onClose={() => setApiFailureNotice(null)} />
      ) : null}

      <nav className="tab-nav">
        <button className={"tab-button" + (activeTab === "qa" ? " active" : "")}
          onClick={() => switchTab("qa")}>
          <Bot size={18} /><span>知识问答</span>
        </button>
        <button className={"tab-button" + (activeTab === "tickets" ? " active" : "")}
          onClick={() => { switchTab("tickets"); void refreshTickets(); }}>
          <ClipboardList size={18} /><span>工单管理</span>
          {pendingActions.length > 0 ? <span className="badge">{pendingActions.length}</span> : null}
        </button>
        <button className={"tab-button" + (activeTab === "graph" ? " active" : "")}
          onClick={() => switchTab("graph")}>
          <Network size={18} /><span>关系图谱</span>
        </button>
        <button className={"tab-button" + (activeTab === "monitor" ? " active" : "")}
          onClick={() => { switchTab("monitor"); void refreshWorkspace(); }}>
          <LineChart size={18} /><span>运行监控</span>
        </button>
      </nav>

      {activeTab === "qa" ? (
        <QAView {...{
          fileInputRef, documents, selectedFile, question, answerMode, retrieverMode, workflowMode,
          embeddingStatus, systemStatus, metricsSummary, chatResponse, isLoadingDocuments,
          isUploading, isAsking, isRebuildingEmbeddings, deletingDocumentId, pendingActions,
          approvingActionId, actorRole, answerFeedback, isSendingFeedback, setSelectedFile,
          setQuestion, setAnswerMode, setRetrieverMode,
          setWorkflowMode, handleUpload, handleAsk, handleDeleteDocument, handleRebuildEmbeddings,
          handleCopyAnswer, handleApprove, handleAnswerFeedback, setChatResponse, setError,
        }} />
      ) : activeTab === "tickets" ? (
        <TicketsView {...{
          ticketList, pendingActions, toolMetrics, toolCalls, isLoadingTickets, approvingActionId,
          actorRole, handleDeleteTicket, handleApprove, handleStatusDraft, statusTag, priorityTag,
          permissionHint: ticketsPermissionHint,
        }} />
      ) : activeTab === "graph" ? (
        <GraphView actorRole={actorRole} setError={setError} />
      ) : (
        <MonitorView metricsSummary={metricsSummary} onRefresh={refreshWorkspace} actorRole={actorRole} />
      )}
    </main>
  );
}

createRoot(document.getElementById("root")!).render(
  <React.StrictMode>
    <App />
  </React.StrictMode>,
);
