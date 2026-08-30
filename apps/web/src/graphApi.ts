import type { ActorRole } from "./apiClient";
import { API_BASE_URL, parseJsonResponse, safeFetch } from "./apiClient";


// V4: 关系图谱 API

export type GraphEntity = {
  name: string;
  entity_type: string;
  type_label: string;
  mention_count: number;
  document_ids: string[];
};

export type GraphRelation = {
  source_name: string;
  source_type: string;
  relation_type: string;
  target_name: string;
  target_type: string;
  evidence: string;
  document_id: string;
  filename: string;
  chunk_index: number;
};

export type GraphOverview = {
  entity_count: number;
  relation_count: number;
  document_count: number;
  entity_types: Record<string, number>;
  relation_types: Record<string, number>;
  built_at: string;
};

export type GraphRebuildResponse = GraphOverview & { duration_ms: number };

export type GraphPathStep = {
  source: string;
  relation: string;
  target: string;
  forward: boolean;
  display: string;
};

export type GraphPath = {
  steps: GraphPathStep[];
  display: string;
};

export type GraphPathQuery = {
  source: string;
  target: string;
  max_depth: number;
  paths: GraphPath[];
};

export async function getGraphOverview(): Promise<GraphOverview> {
  const response = await safeFetch(`${API_BASE_URL}/graph/overview`);
  return parseJsonResponse<GraphOverview>(response);
}

export async function listGraphEntities(entityType = "", keyword = ""): Promise<GraphEntity[]> {
  const params = new URLSearchParams();
  if (entityType) params.set("entity_type", entityType);
  if (keyword) params.set("keyword", keyword);
  const query = params.toString();
  const response = await safeFetch(`${API_BASE_URL}/graph/entities${query ? `?${query}` : ""}`);
  return parseJsonResponse<GraphEntity[]>(response);
}

export async function listGraphRelations(entity = ""): Promise<GraphRelation[]> {
  const params = entity ? `?entity=${encodeURIComponent(entity)}` : "";
  const response = await safeFetch(`${API_BASE_URL}/graph/relations${params}`);
  return parseJsonResponse<GraphRelation[]>(response);
}

export async function queryGraphPaths(source: string, target: string, maxDepth = 3): Promise<GraphPathQuery> {
  const params = new URLSearchParams({ source, target, max_depth: String(maxDepth) });
  const response = await safeFetch(`${API_BASE_URL}/graph/paths?${params.toString()}`);
  return parseJsonResponse<GraphPathQuery>(response);
}

export async function rebuildGraph(actorRole: ActorRole = "operator"): Promise<GraphRebuildResponse> {
  const response = await safeFetch(`${API_BASE_URL}/graph/rebuild`, {
    method: "POST",
    headers: { "X-User-Role": actorRole },
  });
  return parseJsonResponse<GraphRebuildResponse>(response);
}
