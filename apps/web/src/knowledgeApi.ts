import { API_BASE_URL, safeFetch, parseJsonResponse, type ActorRole } from "./apiClient";
import type { DocumentSummary, DocumentUploadResponse, SystemStatus, EmbeddingStatus, EmbeddingRebuildResponse } from "./api";

export async function listDocuments(signal?: AbortSignal): Promise<DocumentSummary[]> {
  const response = await safeFetch(`${API_BASE_URL}/documents`, { signal });
  return parseJsonResponse<DocumentSummary[]>(response);
}

export async function getSystemStatus(signal?: AbortSignal): Promise<SystemStatus> {
  const response = await safeFetch(`${API_BASE_URL}/system/status`, { signal });
  return parseJsonResponse<SystemStatus>(response);
}

export async function uploadDocument(file: File, actorRole: ActorRole = "operator"): Promise<DocumentUploadResponse> {
  const formData = new FormData();
  formData.append("file", file);

  const response = await safeFetch(`${API_BASE_URL}/documents`, {
    method: "POST",
    headers: { "X-User-Role": actorRole },
    body: formData,
  });
  return parseJsonResponse<DocumentUploadResponse>(response);
}

export async function deleteDocument(documentId: string, actorRole: ActorRole = "operator"): Promise<void> {
  const response = await safeFetch(`${API_BASE_URL}/documents/${documentId}`, {
    method: "DELETE",
    headers: { "X-User-Role": actorRole },
  });
  await parseJsonResponse(response);
}

export async function getEmbeddingStatus(signal?: AbortSignal): Promise<EmbeddingStatus> {
  const response = await safeFetch(`${API_BASE_URL}/embeddings/status`, { signal });
  return parseJsonResponse<EmbeddingStatus>(response);
}

export async function rebuildEmbeddings(actorRole: ActorRole = "operator"): Promise<EmbeddingRebuildResponse> {
  const response = await safeFetch(`${API_BASE_URL}/embeddings/rebuild`, {
    method: "POST",
    headers: { "X-User-Role": actorRole },
  });
  return parseJsonResponse<EmbeddingRebuildResponse>(response);
}
