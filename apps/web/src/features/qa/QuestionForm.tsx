import { Loader2, Plus, Send, Square, Video } from "lucide-react";
import type { AnswerMode, RetrieverMode, WorkflowMode } from "../../api";
import type { MemoryMode } from "../../chatApi";
import type { QAViewProps } from "../QAView";

export function QuestionForm(p: Pick<QAViewProps, "answerMode" | "conversation" | "handleAsk" | "isAsking" | "question" | "retrieverMode" | "selectedAssetCount" | "setAnswerMode" | "setQuestion" | "setRetrieverMode" | "setWorkflowMode" | "workflowMode">) {
  return (
<div className="card">
          <form className="chat-form" onSubmit={p.handleAsk}>
			{p.selectedAssetCount > 0 ? <div className="video-scope-note"><Video size={15} />当前限定分析 {p.selectedAssetCount} 个视频；文档仍按当前工作区检索。</div> : null}
            <div className="chat-controls">
              <div className="select-group">
                <label>
                  工作流
                  <select value={p.workflowMode} onChange={(e) => p.setWorkflowMode(e.target.value as WorkflowMode)}>
                    <option value="agentic">多步分析</option>
                    <option value="standard">单轮检索</option>
                  </select>
                </label>
                <label>
                  回答
                  <select value={p.answerMode} onChange={(e) => p.setAnswerMode(e.target.value as AnswerMode)}>
                    <option value="auto">自动选择</option>
                    <option value="local">本地规则</option>
                    <option value="api">模型回答</option>
                  </select>
                </label>
                <label>
                  检索
                  <select value={p.retrieverMode} onChange={(e) => p.setRetrieverMode(e.target.value as RetrieverMode)}>
                    <option value="keyword">关键词</option>
                    <option value="embedding">向量</option>
                    <option value="hybrid">混合检索</option>
                  </select>
                </label>
                <label>
                  连续追问
                  <select value={p.conversation.memoryMode} disabled={p.isAsking}
                    onChange={(event) => p.conversation.setMemoryMode(event.target.value as MemoryMode)}>
                    <option value="window">记住最近四轮</option>
                    <option value="summary">摘要与最近四轮</option>
                    <option value="none">每次独立提问</option>
                  </select>
                </label>
              </div>
              <button className="button subtle" type="button" onClick={p.conversation.newConversation}>
                <Plus size={14} />新建会话
              </button>
            </div>
            <div className="chat-input-row">
              <input
                placeholder="请输入企业知识库问题..."
                value={p.question}
                onChange={(event) => p.setQuestion(event.target.value)}
                disabled={p.isAsking}
              />
              <button className="button" type="submit" disabled={p.isAsking || !p.question.trim()}>
                {p.isAsking ? (
                  <>
                    <Loader2 size={15} />
                    思考中...
                  </>
                ) : (
                  <>
                    <Send size={15} />
                    提问
                  </>
                )}
              </button>
              {p.isAsking ? <button className="button subtle" type="button" onClick={p.conversation.stop}>
                <Square size={14} />停止生成
              </button> : null}
            </div>
          </form>
          {p.conversation.history.length > 0 ? (
            <details className="conversation-history">
              <summary>最近对话（{p.conversation.history.length} 轮）</summary>
              {p.conversation.history.map((turn, index) => <article key={index}>
                <strong>{turn.question}</strong><p>{turn.answer.slice(0, 240)}{turn.answer.length > 240 ? "…" : ""}</p>
              </article>)}
            </details>
          ) : null}
        </div>
  );
}
