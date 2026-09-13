import assert from "node:assert/strict";
import { test } from "node:test";
import { build } from "esbuild";

const result = await build({ stdin: { contents: `export * from "./queryClient";
  export * from "./mediaApi"; export * from "./knowledgeApi"; export * from "./observabilityApi";
  export * from "./ticketApi"; export * from "./graphApi"; export * from "./analysisApi";`,
  resolveDir: `${process.cwd()}/src` }, bundle: true, write: false, format: "esm",
  define: { "import.meta.env": JSON.stringify({ VITE_API_BASE_URL: "http://agent.test", VITE_MEDIA_API_BASE_URL: "http://media.test" }) } });
const api = await import(`data:text/javascript;base64,${Buffer.from(result.outputFiles[0].text).toString("base64")}`);
const session = { tenantId: "tenant-a", userId: "alice", role: "operator", workspaceType: "personal", username: "alice", token: "platform-jwt" };
globalThis.window = { localStorage: { getItem: () => JSON.stringify(session) } };

test("query keys isolate Workspace, owner, role and workspace type while preserving token refresh", () => {
  const key = api.workspaceKey(session, "knowledge");
  for (const change of [{ tenantId: "tenant-b" }, { userId: "bob" }, { role: "viewer" }, { workspaceType: "team" }]) {
    assert.notDeepEqual(api.workspaceKey({ ...session, ...change }, "knowledge"), key);
  }
  assert.deepEqual(api.workspaceKey({ ...session, token: "refreshed-jwt" }, "knowledge"), key);
});

test("deduplicates concurrent reads and disposes slow responses at Workspace boundary", async () => {
  const client = api.createWorkspaceQueryClient();
  const next = api.createWorkspaceQueryClient();
  // Browser GC timers are unnecessary in a Node unit fixture and would keep its process alive.
  for (const cache of [client, next]) cache.setDefaultOptions({ ...cache.getDefaultOptions(),
    queries: { ...cache.getDefaultOptions().queries, gcTime: Infinity } });
  let finish;
  let signal;
  let requests = 0;
  const key = api.workspaceKey(session, "knowledge");
  const queryFn = ({ signal: current }) => {
    requests++; signal = current;
    return new Promise((resolve) => { finish = resolve; });
  };
  const first = client.fetchQuery({ queryKey: key, queryFn }).catch((error) => error);
  const second = client.fetchQuery({ queryKey: key, queryFn }).catch((error) => error);
  assert.equal(requests, 1);
  await api.disposeWorkspaceQueries(client);
  assert.equal(signal.aborted, true);
  finish(["private tenant-a evidence"]);
  await Promise.all([first, second]);
  assert.equal(client.getQueryData(key), undefined);
  assert.equal(next.getQueryData(api.workspaceKey({ ...session, tenantId: "tenant-b" }, "knowledge")), undefined);
  assert.equal(client.getQueryCache().getAll().length, 0);
  await api.disposeWorkspaceQueries(next);
});

test("retries are bounded, authorization failures are not retried and polling backs off", () => {
  assert.equal(api.retryQuery(0, { status: 503 }), true);
  assert.equal(api.retryQuery(2, { status: 503 }), false);
  assert.equal(api.retryQuery(0, { status: 403 }), false);
  assert.equal(api.retryQuery(0, new DOMException("cancelled", "AbortError")), false);
  const now = Date.now();
  const active = { status: "TRANSCRIBING", updatedAt: new Date(now).toISOString() };
  assert.equal(api.mediaPollDelay([active], null, 0, now), 2000);
  assert.equal(api.mediaPollDelay([active], null, 0, now + 70_000), 10_000);
  assert.equal(api.mediaPollDelay([active], null, 0, now + 200_000), 30_000);
  assert.equal(api.mediaPollDelay([{ ...active, status: "COMPLETED" }], null, 0, now), false);
  assert.equal(api.mediaPollDelay([active], { status: 403 }, 1, now), false);
  assert.equal(api.mediaPollDelay(undefined, { status: 503 }, 10, now), 30_000);
});

test("query transports carry the active bearer and the same cancellation signal", async () => {
  const controller = new AbortController();
  const seen = [];
  globalThis.fetch = async (url, options) => {
    seen.push({ url, options });
    return new Response(JSON.stringify(String(url).startsWith("http://media.test") ? { success: true, data: [] } : []),
      { headers: { "Content-Type": "application/json" } });
  };
  const signal = controller.signal;
  await Promise.all([
    api.listMediaTasks(signal), api.getMediaRuntime(signal), api.listMediaTaskStages("task-id", 0, signal),
    api.listWorkspaces(signal), api.listWorkspaceMembers("team-id", signal),
    api.listDocuments(signal), api.getEmbeddingStatus(signal), api.getSystemStatus(signal),
    api.getMetricsSummary(signal), api.getToolMetrics(signal), api.listToolCalls(20, "operator", signal),
    api.listTickets(undefined, signal), api.listPendingActions("pending", "operator", signal),
    api.listChatLogs("", 50, "operator", signal), api.getChatLogDetail(1, "operator", signal),
    api.getGraphOverview(signal), api.listGraphEntities("", "", signal), api.listGraphRelations("", signal),
    api.queryGraphPaths("A", "B", 3, signal), api.listAnalysisSessions(signal), api.listPublicationQueue(signal),
    api.listAnalysisAudit("id", signal), api.getPublicationDeliverables("id", signal),
  ]);
  assert.equal(seen.length, 23);
  for (const { url, options } of seen) {
    assert.equal(options.signal, signal, url);
    assert.equal(options.headers.get("Authorization"), "Bearer platform-jwt", url);
  }
});

test("Media cancellation remains AbortError and is not shown as a connectivity failure", async () => {
  globalThis.fetch = (_url, { signal }) => new Promise((_resolve, reject) => {
    signal.addEventListener("abort", () => reject(signal.reason), { once: true });
  });
  const controller = new AbortController();
  const request = api.listMediaTasks(controller.signal);
  controller.abort();
  await assert.rejects(request, { name: "AbortError" });
});
