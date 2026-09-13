import { Video } from "lucide-react";
import { formatTimestamp } from "../MediaWorkspace";
import type { QAViewProps } from "../QAView";

export function SourceList(p: Pick<QAViewProps, "chatResponse" | "handleOpenVideoEvidence">) {
  return (
<div className="sources-box">
          <div className="sources-title">
            <h3>来源证据</h3>
            <span>{p.chatResponse?.sources.length ?? 0} 条</span>
          </div>
          {!p.chatResponse || p.chatResponse.sources.length === 0 ? (
            <div className="empty-source">暂无来源。上传文档并提问后，这里会显示命中的 chunk。</div>
          ) : (
            p.chatResponse.sources.map((source, index) => (
              <article className="source-item" key={`${source.document_id}-${source.chunk_index}`}>
                <header>
                  <strong>来源 {index + 1}</strong>
                  <span>
					{source.source_type === "video" ? "视频证据" : source.origin_type === "approved_knowledge" ? "已批准知识" : "文档证据"} · {source.filename} · score {source.score}
                  </span>
                </header>
                <p>{source.content}</p>
				{source.source_type === "video" && source.asset_id && source.start_ms != null ? (
					<button className="evidence-jump" type="button" onClick={() => p.handleOpenVideoEvidence(source.asset_id!, source.start_ms!)}>
						<Video size={14} />播放 {formatTimestamp(source.start_ms)}–{formatTimestamp(source.end_ms ?? source.start_ms)}
					</button>
				) : null}
              </article>
            ))
          )}
        </div>
  );
}
