import { QueryClient } from "@tanstack/react-query";
import type { WorkspaceSession } from "./session";
import type { MediaTask } from "./mediaApi";

export function workspaceIdentity(session: WorkspaceSession): string {
  return JSON.stringify([session.tenantId, session.userId, session.role, session.workspaceType]);
}

export function workspaceKey(session: WorkspaceSession, domain: string) {
  return ["workspace", workspaceIdentity(session), domain] as const;
}

export function retryQuery(failures: number, error: unknown): boolean {
  if (error instanceof Error && error.name === "AbortError") return false;
  const status = (error as { status?: number } | null)?.status;
  if (status && status >= 400 && status < 500 && status !== 408 && status !== 429) return false;
  return failures < 2;
}

export const retryDelay = (attempt: number) => Math.min(1000 * 2 ** attempt, 10_000);

export function createWorkspaceQueryClient(): QueryClient {
  return new QueryClient({ defaultOptions: {
    queries: { staleTime: 15_000, gcTime: 300_000, retry: retryQuery, retryDelay, refetchOnWindowFocus: true },
    // Approval, uploads and other writes are never automatically repeated by the UI.
    mutations: { retry: false },
  } });
}

export async function disposeWorkspaceQueries(client: QueryClient): Promise<void> {
  const cancelled = client.cancelQueries();
  client.clear();
  await cancelled;
}

export function mediaPollDelay(tasks: MediaTask[] | undefined, error: unknown, failures: number, now = Date.now()): number | false {
  if (error) return retryQuery(0, error) ? Math.min(2000 * 2 ** Math.min(failures, 4), 30_000) : false;
  const active = tasks?.filter((task) => !["COMPLETED", "FAILED"].includes(task.status)) ?? [];
  if (!active.length) return false;
  const latest = Math.max(...active.map((task) => Date.parse(task.updatedAt)));
  const idle = Number.isFinite(latest) ? Math.max(0, now - latest) : 0;
  return idle < 15_000 ? 2000 : idle < 60_000 ? 5000 : idle < 180_000 ? 10_000 : 30_000;
}
