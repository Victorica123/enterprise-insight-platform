import assert from "node:assert/strict";
import { test } from "node:test";
import { build } from "esbuild";
import { createRequire } from "node:module";

// Render the real pages with their Query and Workspace providers. A viewer can
// still read evidence and ask questions, but cannot start governed mutations.
const built = await build({
  stdin: { resolveDir: `${process.cwd()}/src`, loader: "tsx", contents: `
    import React from "react";
    import { renderToStaticMarkup } from "react-dom/server";
    import { QueryClientProvider } from "@tanstack/react-query";
    import { createWorkspaceQueryClient, workspaceKey } from "./queryClient";
    import { WorkspaceContext } from "./workspaceContext";
    import { MediaWorkspace } from "./features/MediaWorkspace";
    import { QAView } from "./features/QAView";
    import { AnalysisWorkspace } from "./features/AnalysisWorkspace";
    const noop = () => {};
    export function render(page, role, status = "DRAFT_READY", requester = "other") {
      const session = { userId: "alice", tenantId: "team", workspaceType: "team", role };
      const client = createWorkspaceQueryClient();
      client.setDefaultOptions({ queries: { gcTime: Infinity, retry: false } });
      let component;
      if (page === "media") {
        const base = { fileName: "evidence.mp4", createdAt: "2026-09-13T00:00:00Z",
          transcriptSegments: [], transcriptVersion: 1, mediaRetained: true };
        component = <MediaWorkspace session={session} tasks={[
          { ...base, taskId: "completed", videoId: "video-1", status: "COMPLETED" },
          { ...base, taskId: "failed", videoId: "video-2", status: "FAILED" },
        ]} runtime={null} loading={false} selectedAssetIds={[]} onSelectionChange={noop}
          onRefresh={noop} onError={noop} onPlay={noop} />;
      } else if (page === "qa") {
        component = <QAView actorRole={role} fileInputRef={{ current: null }}
          documents={[{ document_id: "doc", filename: "evidence.md", chunk_count: 1,
            created_at: "2026-09-13T00:00:00Z" }]} selectedFile={{ name: "new.md" }}
          question="What does the evidence say?" answerMode="local" retrieverMode="keyword"
          workflowMode="standard" systemStatus={{ status: "ok", document_count: 1 }}
          conversation={{ history: [], memoryMode: "window" }} chatResponse={null}
          answerFeedback={null} pendingActions={[]} selectedAssetCount={0}
          setQuestion={noop} setAnswerMode={noop} setRetrieverMode={noop} setWorkflowMode={noop} />;
      } else {
        const active = { session_id: "analysis", owner_id: "alice", objective: "Review evidence",
          status, created_at: "2026-09-13T00:00:00Z", checkpoint_version: 1,
          evidence_snapshot_sha256: "test-hash", evidence_revision: 1, current_stage: 6,
          stages: [], open_questions: [], resume_token: "resume",
          publication: { policy: "FOUR_EYES", requested_by: requester, approval_token: "approval" },
          prd: { title: "Evidence PRD", executive_summary: "Summary", requirements: [] } };
        client.setQueryData([...workspaceKey(session, "analysis"), "sessions"], [active]);
        client.setQueryData([...workspaceKey(session, "analysis"), "deliverables", "analysis"], {
          version: { version_number: 1, content_sha256: "published-hash" }, knowledge_candidates: [],
          action_items: [{ action_item_id: "action", owner_id: "alice", status: "DRAFT", title: "Follow up" }],
        });
        component = <AnalysisWorkspace selectedAssetIds={[]} onPlayEvidence={noop} onError={noop} />;
      }
      const html = renderToStaticMarkup(<WorkspaceContext.Provider value={session}>
        <QueryClientProvider client={client}>{component}</QueryClientProvider>
      </WorkspaceContext.Provider>);
      client.clear();
      return html;
    }
  ` },
  bundle: true, write: false, platform: "node", format: "cjs", jsx: "automatic", loader: { ".css": "empty" },
  define: { "import.meta.env": JSON.stringify({ VITE_API_BASE_URL: "http://agent.test", VITE_MEDIA_API_BASE_URL: "http://media.test" }) },
});
const compiled = { exports: {} };
new Function("require", "module", "exports", built.outputFiles[0].text)(createRequire(import.meta.url), compiled, compiled.exports);
const { render } = compiled.exports;

function button(html, label) {
  const found = [...html.matchAll(/<button\b([^>]*)>([\s\S]*?)<\/button>/g)].find(([, attrs, content]) =>
    attrs.includes(`title="${label}"`) || content.replace(/<[^>]+>/g, "").trim() === label);
  assert.ok(found, `Missing button: ${label}`);
  return found[1];
}

function disabled(attrs) { return /\bdisabled=""/.test(attrs); }

test("viewer can select and play media but cannot upload, retry or delete", () => {
  for (const role of ["viewer", "operator", "admin"]) {
    const html = render("media", role);
    const readOnly = role === "viewer";
    assert.equal(disabled(html.match(/<input\b[^>]*type="file"[^>]*>/)[0]), readOnly);
    assert.equal(disabled(button(html, "重试")), readOnly);
    assert.equal(disabled(button(html, "删除")), readOnly);
    assert.equal(disabled(button(html, "播放")), false);
    assert.equal(disabled(button(html, "纳入 Agent 分析范围")), false);
    assert.equal(disabled(button(html, "上传视频")), true, "A file must be selected before uploading");
  }
});

test("viewer can ask questions but cannot upload, rebuild or delete documents", () => {
  for (const role of ["viewer", "operator", "admin"]) {
    const html = render("qa", role);
    const readOnly = role === "viewer";
    assert.equal(disabled(html.match(/<input\b[^>]*type="file"[^>]*>/)[0]), readOnly);
    for (const label of ["上传", "一键重建所有 chunk 的本地 embedding", "删除文档"]) {
      assert.equal(disabled(button(html, label)), readOnly, label);
    }
    assert.equal(disabled(button(html, "提问")), false);
  }
});

test("analysis writes require a writer while publication keeps four-eyes separation", () => {
  for (const role of ["viewer", "operator", "admin"]) {
    const readOnly = role === "viewer";
    const draft = render("analysis", role);
    assert.equal(disabled(button(draft, "开始分析")), readOnly);
    assert.equal(disabled(button(draft, "申请正式发布")), readOnly);
    assert.equal(disabled(button(render("analysis", role, "WAITING_CONFIRMATION"), "确认并继续")), readOnly);
    assert.equal(render("analysis", role, "PUBLISH_PENDING").includes("确认正式发布</button>"), !readOnly);
    assert.equal(render("analysis", role, "PUBLISH_PENDING", "alice").includes("确认正式发布</button>"), false);
    assert.equal(render("analysis", role, "PUBLISHED").includes("进入工单审批</button>"), !readOnly);
  }
});
