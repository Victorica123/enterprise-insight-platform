import assert from "node:assert/strict";
import { beforeEach, test } from "node:test";
import { build } from "esbuild";

// Compile the real browser module with the same bundler used by Vite. Only
// browser storage and HTTP are replaced; no identity provider is contacted.
const result = await build({
  entryPoints: ["src/oidc.ts"], bundle: true, write: false, format: "esm",
  define: { "import.meta.env": JSON.stringify({
    VITE_OIDC_ENABLED: "true", VITE_OIDC_ISSUER: "https://identity.test/realm",
    VITE_MEDIA_API_BASE_URL: "http://media.test",
  }) },
});
const oidc = await import(`data:text/javascript;base64,${Buffer.from(result.outputFiles[0].text).toString("base64")}`);
const refreshKey = "enterprise-insight.oidc.refresh-token";
const values = new Map();
const calls = [];
const replies = [];
globalThis.sessionStorage = {
  getItem: (key) => values.get(key) ?? null,
  setItem: (key, value) => values.set(key, value),
  removeItem: (key) => values.delete(key),
};
globalThis.window = { localStorage: globalThis.sessionStorage };
globalThis.fetch = async (url, init) => {
  calls.push({ url, init });
  const reply = replies.shift();
  assert.ok(reply, "Unexpected HTTP request");
  return typeof reply === "function" ? reply() : reply;
};
const json = (payload, status = 200) => new Response(JSON.stringify(payload), { status });
const session = (tenantId = "team", role = "viewer") => ({
  tenantId, role, userId: "user", username: "user", workspaceType: tenantId === "team" ? "team" : "personal", token: "new-platform-token",
});
const success = (data = session()) => json({ success: true, data });
beforeEach(() => {
  oidc.clearOidcSession();
  values.clear(); calls.length = 0; replies.length = 0;
  sessionStorage.setItem(refreshKey, "old-refresh");
});

test("refresh rotates the credential and requests current workspace authorization", async () => {
  replies.push(json({ access_token: "external", refresh_token: "rotated" }), success());
  assert.deepEqual(await oidc.refreshOidcLogin("team"), session());
  assert.equal(calls[0].init.body.get("grant_type"), "refresh_token");
  assert.equal(calls[0].init.body.get("refresh_token"), "old-refresh");
  assert.equal(calls[1].init.headers.get("X-Workspace-Id"), "team");
  assert.equal(calls[1].init.headers.get("Authorization"), "Bearer external");
  assert.equal(sessionStorage.getItem(refreshKey), "rotated");
});

test("removed membership falls back to personal workspace on Media 404 only", async () => {
  replies.push(json({ access_token: "external" }), json({ message: "not found" }, 404), success(session("personal")));
  assert.equal((await oidc.refreshOidcLogin("team")).tenantId, "personal");
  assert.equal(calls[2].init.headers.has("X-Workspace-Id"), false);
});

test("outage or rejected identity never silently switches workspace", async () => {
  for (const status of [401, 403, 500]) {
    calls.length = 0;
    replies.push(json({ access_token: "external" }), json({ message: "unavailable" }, status));
    await assert.rejects(oidc.refreshOidcLogin("team"), (error) => error.status === status);
    assert.equal(calls.length, 2);
  }
});

test("simultaneous refreshes share one rotating provider grant", async () => {
  replies.push(json({ access_token: "external", refresh_token: "rotated" }), success(), success(session("other")));
  const sessions = await Promise.all([oidc.refreshOidcLogin("team"), oidc.refreshOidcLogin("other")]);
  assert.deepEqual(sessions.map((value) => value.tenantId), ["team", "other"]);
  assert.equal(calls.filter((call) => call.url.endsWith("/token")).length, 1);
});

test("logout fences a late provider response before it can restore credentials", async () => {
  let resolve;
  replies.push(() => new Promise((done) => { resolve = done; }));
  const refresh = oidc.refreshOidcLogin("team");
  oidc.clearOidcSession();
  resolve(json({ access_token: "external", refresh_token: "late" }));
  await assert.rejects(refresh, /会话已结束/);
  assert.equal(sessionStorage.getItem(refreshKey), null);
  assert.equal(calls.length, 1);
});

test("logout fences a late platform exchange response", async () => {
  let resolve;
  let started;
  const exchanging = new Promise((done) => { started = done; });
  replies.push(json({ access_token: "external", refresh_token: "rotated" }), () => {
    started();
    return new Promise((done) => { resolve = done; });
  });
  const refresh = oidc.refreshOidcLogin("team");
  await exchanging;
  oidc.clearOidcSession();
  resolve(success());
  await assert.rejects(refresh, /会话已结束/);
  assert.equal(sessionStorage.getItem(refreshKey), null);
});

test("expired provider grant clears refresh credentials", async () => {
  replies.push(json({ error: "invalid_grant" }, 400));
  await assert.rejects(oidc.refreshOidcLogin("team"));
  assert.equal(oidc.oidcRefreshAvailable(), false);
  assert.equal(calls.length, 1);
});
