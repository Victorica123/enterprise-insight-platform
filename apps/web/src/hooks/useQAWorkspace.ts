import * as React from "react";
import { useQueryClient } from "@tanstack/react-query";
import { deleteDocument, rebuildEmbeddings, uploadDocument } from "../knowledgeApi";
import { submitFeedback } from "../observabilityApi";
import type { AnswerMode, RetrieverMode, WorkflowMode } from "../api";
import type { WorkspaceSession } from "../session";
import type { QAViewProps } from "../features/QAView";
import { type ApiFailureNotice, getApiFailureReason, getErrorMessage } from "../features/common";
import { workspaceIdentity, workspaceKey } from "../queryClient";
import { useConversation } from "./useConversation";
import { useKnowledgeWorkspace } from "./useKnowledgeWorkspace";
import { useTicketsWorkspace } from "./useTicketsWorkspace";

export function useQAWorkspace(session: WorkspaceSession, selectedAssetIds: string[],
  setError: (message: string | null) => void, handleOpenVideoEvidence: (assetId: string, startMs: number) => void) {
  const actorRole = session.role;
  const fileInputRef = React.useRef<HTMLInputElement | null>(null);
  const client = useQueryClient();
  const conversation = useConversation(workspaceIdentity(session));
  const { chatResponse, setChatResponse, isAsking } = conversation;
  const { documents, embeddingStatus, systemStatus, metricsSummary, isLoadingDocuments,
    refreshWorkspace, setEmbeddingStatus, setSystemStatus } = useKnowledgeWorkspace(session, setError);
  const tickets = useTicketsWorkspace(session, setError);
  const { pendingActions, approvingActionId, handleApprove, refreshTickets } = tickets;
  const mounted = React.useRef(true);
  React.useEffect(() => { mounted.current = true; return () => { mounted.current = false; }; }, []);
  const [selectedFile, setSelectedFile] = React.useState<File | null>(null);
  const [question, setQuestion] = React.useState("客户 A 的项目为什么延期？");
  const [answerMode, setAnswerMode] = React.useState<AnswerMode>("auto");
  const [retrieverMode, setRetrieverMode] = React.useState<RetrieverMode>("keyword");
  const [workflowMode, setWorkflowMode] = React.useState<WorkflowMode>("agentic");
  const [isUploading, setIsUploading] = React.useState(false);
  const [isRebuildingEmbeddings, setIsRebuildingEmbeddings] = React.useState(false);
  const [deletingDocumentId, setDeletingDocumentId] = React.useState<string | null>(null);
  const [apiFailureNotice, setApiFailureNotice] = React.useState<ApiFailureNotice | null>(null);
  const [answerFeedback, setAnswerFeedback] = React.useState<"up" | "down" | null>(null);
  const [isSendingFeedback, setIsSendingFeedback] = React.useState(false);

  async function handleUpload(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (actorRole === "viewer") return;
    if (!selectedFile) {
      setError("请选择一个 .txt、.md 或 .pdf 文件。");
      return;
    }
    setIsUploading(true);
    setError(null);
    try {
      await uploadDocument(selectedFile, actorRole);
      if (!mounted.current) return;
      setSelectedFile(null);
      if (fileInputRef.current) {
        fileInputRef.current.value = "";
      }
      await refreshWorkspace();
      void client.invalidateQueries({ queryKey: workspaceKey(session, "graph") });
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
    setError(null);
    setApiFailureNotice(null);
    setAnswerFeedback(null);
    try {
      const response = await conversation.ask({ question: question.trim(), answer_mode: answerMode,
        retriever_mode: retrieverMode, workflow_mode: workflowMode, asset_ids: selectedAssetIds });
      if (!response) return;
      const failedApiStep = response.trace.find(
        (step) => step.name === "answer" && ["api_failed", "local_fallback"].includes(step.status),
      );
      // `auto` with no configured key is an expected local capability, not a
      // failed user action. Keep the blocking dialog for an explicit API
      // request or for a provider call that was actually attempted and failed.
      if (failedApiStep && (answerMode === "api" || failedApiStep.status === "api_failed")) {
        setApiFailureNotice({
          reason: getApiFailureReason(failedApiStep.detail),
          requestedMode: answerMode,
        });
      }
      void refreshWorkspace();
      void refreshTickets();
    } catch (caught) {
      setError(getErrorMessage(caught));
    }
  }

  async function handleDeleteDocument(documentId: string) {
    if (actorRole === "viewer") return;
    const target = documents.find((document) => document.document_id === documentId);
    const confirmed = window.confirm("确定删除文档「" + (target?.filename ?? documentId) + "」吗？");
    if (!confirmed) return;
    setDeletingDocumentId(documentId);
    setError(null);
    try {
      await deleteDocument(documentId, actorRole);
      if (!mounted.current) return;
      if (chatResponse?.sources.some((source) => source.document_id === documentId)) {
        setChatResponse(null);
      }
      await refreshWorkspace();
      void client.invalidateQueries({ queryKey: workspaceKey(session, "graph") });
    } catch (caught) {
      setError(getErrorMessage(caught));
    } finally {
      setDeletingDocumentId(null);
    }
  }

  async function handleRebuildEmbeddings() {
    if (actorRole === "viewer") return;
    setIsRebuildingEmbeddings(true);
    setError(null);
    try {
      const result = await rebuildEmbeddings(actorRole);
      if (!mounted.current) return;
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

  async function handleAnswerFeedback(rating: "up" | "down") {
    if (!chatResponse?.log_id || answerFeedback) return;
    setIsSendingFeedback(true);
    setError(null);
    try {
      await submitFeedback(chatResponse.log_id, rating);
      if (!mounted.current) return;
      setAnswerFeedback(rating);
    } catch (caught) {
      setError(getErrorMessage(caught));
    } finally {
      setIsSendingFeedback(false);
    }
  }

  const props: QAViewProps = {
    fileInputRef, documents, selectedFile, question, answerMode, retrieverMode, workflowMode, conversation,
    embeddingStatus, systemStatus, metricsSummary, chatResponse, isLoadingDocuments,
    isUploading, isAsking, isRebuildingEmbeddings, deletingDocumentId, pendingActions,
    approvingActionId, actorRole, answerFeedback, isSendingFeedback, setSelectedFile,
    setQuestion, setAnswerMode, setRetrieverMode, setWorkflowMode, handleUpload, handleAsk,
    handleDeleteDocument, handleRebuildEmbeddings, handleCopyAnswer, handleApprove, handleAnswerFeedback,
    setChatResponse, setError, selectedAssetCount: selectedAssetIds.length, handleOpenVideoEvidence,
  };
  return { props, tickets, refreshWorkspace, apiFailureNotice, closeApiFailure: () => setApiFailureNotice(null) };
}
