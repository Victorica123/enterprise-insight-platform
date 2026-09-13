import { Bot, CheckCircle2, Coins, Copy, ThumbsDown, ThumbsUp, X } from "lucide-react";
import type { QAViewProps } from "../QAView";

export function AnswerStream(p: Pick<QAViewProps, "answerFeedback" | "chatResponse" | "conversation" | "handleAnswerFeedback" | "handleCopyAnswer" | "isSendingFeedback" | "setChatResponse" | "setQuestion">) {
  return (
<div className="answer-box">
          <div className="answer-title">
            <div>
              <Bot size={19} />
              <h3>回答</h3>
              {p.chatResponse?.token_usage ? (
                <span className="token-pill" title={`prompt ${p.chatResponse.token_usage.prompt_tokens} + completion ${p.chatResponse.token_usage.completion_tokens}`}>
                  <Coins size={13} />
                  {p.chatResponse.token_usage.total_tokens} tokens
                  {p.chatResponse.token_usage.estimated_cost_usd > 0
                    ? ` · $${p.chatResponse.token_usage.estimated_cost_usd.toFixed(5)}`
                    : ""}
                </span>
              ) : null}
            </div>
            <div className="answer-actions">
              <button
                className={"icon-button subtle feedback" + (p.answerFeedback === "up" ? " active-up" : "")}
                type="button"
                onClick={() => void p.handleAnswerFeedback("up")}
                disabled={!p.chatResponse?.log_id || p.isSendingFeedback || p.answerFeedback !== null}
                title={p.answerFeedback === "up" ? "已标记有帮助" : "答案有帮助"}
              >
                <ThumbsUp size={16} />
              </button>
              <button
                className={"icon-button subtle feedback" + (p.answerFeedback === "down" ? " active-down" : "")}
                type="button"
                onClick={() => void p.handleAnswerFeedback("down")}
                disabled={!p.chatResponse?.log_id || p.isSendingFeedback || p.answerFeedback !== null}
                title={p.answerFeedback === "down" ? "已标记待改进" : "答案待改进"}
              >
                <ThumbsDown size={16} />
              </button>
              <button
                className="icon-button subtle"
                type="button"
                onClick={() => void p.handleCopyAnswer()}
                disabled={!p.chatResponse?.answer}
                title="复制回答"
              >
                <Copy size={16} />
              </button>
              <button
                className="icon-button subtle"
                type="button"
                onClick={() => p.setChatResponse(null)}
                disabled={!p.chatResponse}
                title="清空回答"
              >
                <X size={16} />
              </button>
            </div>
          </div>
          {p.conversation.streamStage ? <p className="stream-status" role="status">{p.conversation.streamStage}</p> : null}
          <pre aria-busy={p.conversation.isAsking}>{p.chatResponse?.answer ?? (p.conversation.streamText || "回答会显示在这里。")}</pre>
          {p.chatResponse?.follow_up?.length ? <div className="follow-up-questions">
            {p.chatResponse.follow_up.map((question) => <button className="button subtle" type="button"
              key={question} onClick={() => p.setQuestion(question)}>{question}</button>)}
          </div> : null}
          {p.answerFeedback ? (
            <div className="feedback-ack">
              <CheckCircle2 size={14} />
              反馈已记录，会体现在运行监控的满意度指标中。
            </div>
          ) : null}
        </div>
  );
}
