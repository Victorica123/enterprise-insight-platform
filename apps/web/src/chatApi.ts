import type { AnswerMode, ChatResponse, RetrieverMode, WorkflowMode } from "./api";
import { API_BASE_URL, parseJsonResponse, safeFetch } from "./apiClient";

export type MemoryMode = "none" | "window" | "summary";
export type ChatInput = {
  question: string;
  answer_mode: AnswerMode;
  retriever_mode: RetrieverMode;
  workflow_mode: WorkflowMode;
  asset_ids: string[];
  conversation_id?: string | null;
  memory_mode?: MemoryMode;
};

export type ChatStreamEvent = {
  type: "plan" | "stage" | "delta" | "sources" | "follow_up" | "done" | "error";
  content: unknown;
  timestamp: string;
  conversation_id: string | null;
  exchange_id: string;
};

/** Incrementally decode SSE, including UTF-8 characters split across network chunks. */
export async function consumeChatStream(
  body: ReadableStream<Uint8Array>, onEvent: (event: ChatStreamEvent) => void,
): Promise<ChatResponse> {
  const reader = body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";
  let exchangeId: string | null = null;
  let result: ChatResponse | null = null;
  function consume(frame: string) {
    const data = frame.split(/\r?\n/).filter((line) => line.startsWith("data:"))
      .map((line) => line.slice(5).trimStart()).join("\n");
    if (!data) return;
    const event = JSON.parse(data) as ChatStreamEvent;
    if (!event || typeof event.exchange_id !== "string" || typeof event.type !== "string") {
      throw new Error("问答事件格式无效。");
    }
    if (exchangeId && event.exchange_id !== exchangeId) throw new Error("问答事件不属于同一次请求。");
    exchangeId = event.exchange_id;
    if (event.type === "error") {
      const error = event.content as { message?: string };
      throw new Error(error?.message || "本次问答未完成。");
    }
    if (event.type === "done") {
      const response = event.content as ChatResponse;
      if (!response || typeof response.answer !== "string" || !Array.isArray(response.sources)) {
        throw new Error("问答完成事件缺少回答或证据。");
      }
      result = { ...response, trace: response.trace ?? [], agent_summary: response.agent_summary ?? null,
        pending_actions: response.pending_actions ?? [], token_usage: response.token_usage ?? null, log_id: response.log_id ?? 0 };
    }
    onEvent(event);
  }
  try {
    while (true) {
      const { value, done } = await reader.read();
      buffer += decoder.decode(value, { stream: !done });
      if (buffer.length > 2_000_000) throw new Error("单条问答事件过大。");
      let boundary: RegExpMatchArray | null;
      while ((boundary = buffer.match(/\r?\n\r?\n/))) {
        const index = boundary.index!;
        consume(buffer.slice(0, index));
        buffer = buffer.slice(index + boundary[0].length);
      }
      if (done) break;
    }
    if (!result) throw new Error("连接已中断，未收到完整回答；可以重新提问。");
    return result;
  } finally {
    await reader.cancel().catch(() => undefined);
    reader.releaseLock();
  }
}

export async function streamQuestion(input: ChatInput, onEvent: (event: ChatStreamEvent) => void, signal: AbortSignal): Promise<ChatResponse> {
  const response = await safeFetch(`${API_BASE_URL}/chat/stream`, {
    method: "POST", headers: { "Content-Type": "application/json", Accept: "text/event-stream" },
    body: JSON.stringify(input), signal,
  });
  if (!response.ok) await parseJsonResponse(response);
  if (!response.body || !response.headers.get("content-type")?.includes("text/event-stream")) {
    throw new Error("后端未返回可读取的问答流。");
  }
  return consumeChatStream(response.body, onEvent);
}
