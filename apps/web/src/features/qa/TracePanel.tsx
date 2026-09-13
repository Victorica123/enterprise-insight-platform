import { Workflow } from "lucide-react";
import type { QAViewProps } from "../QAView";

export function TracePanel(p: Pick<QAViewProps, "chatResponse">) {
  return (
<div className="trace-box">
          <div className="answer-title">
            <div>
              <Workflow size={19} />
              <h3>执行轨迹</h3>
            </div>
          </div>
          {!p.chatResponse || p.chatResponse.trace.length === 0 ? (
            <div className="empty-source">暂无轨迹。提问后，这里会显示检索和回答路径。</div>
          ) : (
            <ol className="trace-list">
              {p.chatResponse.trace.map((step, index) => (
                <li className="trace-item" key={`${step.name}-${index}`}>
                  <div>
                    <strong>{step.name}</strong>
                    <span>{step.status}{step.duration_ms != null ? ` · ${step.duration_ms.toFixed(1)} ms` : ""}</span>
                  </div>
                  <p>{step.detail}</p>
                </li>
              ))}
            </ol>
          )}
        </div>
  );
}
