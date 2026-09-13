import assert from "node:assert/strict";
import { test } from "node:test";
import { build } from "esbuild";

const result = await build({ entryPoints: ["src/chatApi.ts"], bundle: true, write: false, format: "esm",
  define: { "import.meta.env": JSON.stringify({ VITE_API_BASE_URL: "http://agent.test" }) } });
const { consumeChatStream, streamQuestion } = await import(`data:text/javascript;base64,${Buffer.from(result.outputFiles[0].text).toString("base64")}`);
const encoder = new TextEncoder();
const event = (type, content, exchange = "exchange-1") => ({ type, content, timestamp: "2026-09-13T00:00:00Z", conversation_id: "conversation-1", exchange_id: exchange });
const frame = (value) => `event: ${value.type}\r\ndata: ${JSON.stringify(value)}\r\n\r\n`;
const stream = (parts) => new ReadableStream({ start(controller) { for (const part of parts) controller.enqueue(part); controller.close(); } });
const final = { answer: "客户A负责人是李四。", sources: [], trace: [] };

test("SSE parser reassembles split UTF-8, CRLF, comments and final response", async () => {
  const bytes = encoder.encode(": keepalive\r\n\r\n" + frame(event("delta", { text: "中", provisional: true })) + frame(event("done", final)));
  const parts = Array.from(bytes, (byte) => new Uint8Array([byte]));
  const events = [];
  const response = await consumeChatStream(stream(parts), (value) => events.push(value));
  assert.equal(events[0].content.text, "中");
  assert.equal(response.answer, final.answer);
  assert.deepEqual(response.pending_actions, []);
});

test("provisional output cannot become a successful result without done", async () => {
  await assert.rejects(consumeChatStream(stream([encoder.encode(frame(event("delta", { text: "未核验" })))]), () => {}), /未收到完整回答/);
});

test("server error ends stream and does not produce a final answer", async () => {
  await assert.rejects(consumeChatStream(stream([encoder.encode(frame(event("error", { message: "请重试" })))]), () => {}), /请重试/);
});

test("events from another exchange are rejected", async () => {
  await assert.rejects(consumeChatStream(stream([encoder.encode(frame(event("stage", {})) + frame(event("done", final, "other")))]), () => {}), /同一次请求/);
});

test("a delta is observable while the rest of the response is still pending", async () => {
  let controller;
  const body = new ReadableStream({ start(value) { controller = value; } });
  const events = [];
  let finished = false;
  const pending = consumeChatStream(body, (value) => events.push(value)).then(() => { finished = true; });
  controller.enqueue(encoder.encode(frame(event("delta", { text: "首字" }))));
  await new Promise((resolve) => setImmediate(resolve));
  assert.equal(events[0].content.text, "首字");
  assert.equal(finished, false);
  controller.enqueue(encoder.encode(frame(event("done", final)))); controller.close();
  await pending;
});

test("stream request sends the active bearer and AbortSignal without role headers", async () => {
  const token = { token: "signed-platform-token", userId: "alice", username: "alice", tenantId: "tenant-a", workspaceType: "personal", role: "operator" };
  globalThis.window = { localStorage: { getItem: () => JSON.stringify(token) } };
  const abort = new AbortController();
  let request;
  globalThis.fetch = async (_url, init) => { request = init; return new Response(stream([encoder.encode(frame(event("done", final)))]), { headers: { "Content-Type": "text/event-stream" } }); };
  await streamQuestion({ question: "客户A", answer_mode: "local", retriever_mode: "hybrid", workflow_mode: "agentic", asset_ids: [] }, () => {}, abort.signal);
  assert.equal(request.signal, abort.signal);
  assert.equal(request.headers.get("Authorization"), "Bearer signed-platform-token");
  assert.equal(request.headers.has("X-User-Role"), false);
});
