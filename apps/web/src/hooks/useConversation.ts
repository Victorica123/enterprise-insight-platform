import * as React from "react";
import type { ChatResponse } from "../api";
import { streamQuestion, type ChatInput, type MemoryMode } from "../chatApi";

const stageLabels: Record<string, string> = {
  preparation: "正在准备问题", classify_intent: "正在理解问题", decide_mode: "正在选择处理方式",
  plan_queries: "正在规划检索", question_received: "已收到问题", query_expansion: "正在补充检索词",
  retrieve: "正在检索证据", retrieve_round_1: "正在检索证据", retrieve_round_2: "正在补充证据",
  evidence_check: "正在核对证据", evidence_check_1: "正在核对证据", evidence_check_2: "正在核对证据",
  answer: "正在生成回答", citation_check: "正在核验引用", graph_lookup: "正在核对关联信息",
};

export function useConversation(identity: string) {
  const [chatResponse, setChatResponse] = React.useState<ChatResponse | null>(null);
  const [isAsking, setIsAsking] = React.useState(false);
  const [streamText, setStreamText] = React.useState("");
  const [streamStage, setStreamStage] = React.useState("");
  const [memoryMode, setMemoryMode] = React.useState<MemoryMode>("window");
  const [history, setHistory] = React.useState<{ question: string; answer: string }[]>([]);
  const conversationId = React.useRef<string | null>(null);
  const active = React.useRef<AbortController | null>(null);
  const generation = React.useRef(0);

  const stop = React.useCallback(() => {
    generation.current += 1;
    active.current?.abort();
    active.current = null;
    setIsAsking(false);
    setStreamStage("已停止生成");
  }, []);
  const newConversation = React.useCallback(() => {
    stop();
    conversationId.current = null;
    setChatResponse(null);
    setStreamText("");
    setStreamStage("");
    setHistory([]);
  }, [stop]);

  React.useEffect(() => {
    newConversation();
    return () => { generation.current += 1; active.current?.abort(); };
  }, [identity, newConversation]);

  async function ask(input: ChatInput): Promise<ChatResponse | null> {
    active.current?.abort();
    const controller = new AbortController();
    active.current = controller;
    const current = ++generation.current;
    setIsAsking(true);
    setStreamText("");
    setChatResponse(null);
    setStreamStage("正在准备问题");
    try {
      const response = await streamQuestion({ ...input, conversation_id: conversationId.current, memory_mode: memoryMode }, (event) => {
        if (current !== generation.current) return;
        if (event.conversation_id) conversationId.current = event.conversation_id;
        if (event.type === "delta") {
          const content = event.content as { text?: string };
          if (typeof content?.text === "string") setStreamText((previous) => previous + content.text);
          setStreamStage("正在生成回答，引用核验后显示最终结果");
        } else if (event.type === "stage") {
          const content = event.content as { name?: string };
          if (content?.name && stageLabels[content.name]) setStreamStage(stageLabels[content.name]);
        }
      }, controller.signal);
      if (current !== generation.current) return null;
      setChatResponse(response);
      setStreamText("");
      setStreamStage("回答已完成");
      setHistory((previous) => [...previous, { question: input.question, answer: response.answer }].slice(-4));
      return response;
    } catch (error) {
      if (controller.signal.aborted || current !== generation.current) return null;
      setStreamStage("本次问答未完成");
      throw error;
    } finally {
      if (current === generation.current) { active.current = null; setIsAsking(false); }
    }
  }

  return { chatResponse, setChatResponse, isAsking, streamText, streamStage, history,
    memoryMode, setMemoryMode, ask, stop, newConversation };
}

export type ConversationController = ReturnType<typeof useConversation>;
