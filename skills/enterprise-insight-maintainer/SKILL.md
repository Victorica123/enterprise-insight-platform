---
name: enterprise-insight-maintainer
description: Maintain, review, debug, extend, or release the Enterprise Insight Platform monorepo across its Spring media service, FastAPI agent service, React application, contracts, semantic project knowledge, and quality evidence. Use only for this product and its migration sources.
metadata:
  short-description: Maintain the Enterprise Insight Platform
---

# Enterprise Insight Maintainer

Keep this repository a coherent product rather than two demos placed side by side.

## Start every task

1. Resolve the repository root and read `AGENTS.md`.
2. Read `knowledge/INDEX.md`, then load only the references it routes to for the task. For onboarding, broad review, or safe slimming, read `docs/START_HERE.md` before opening implementation files.
3. For cross-service, architectural, RAG, unfamiliar, or broad tasks, run `python scripts/query_project_knowledge.py "<task>" --repo <root>` from this Skill directory. Read the returned source ranges; never treat index previews as truth. A known single-file task can use the manual route directly.
4. Inspect the affected service and its tests before changing code. Treat the original repositories as read-only migration sources.
5. Check the working tree and preserve unrelated user changes.

## Product invariants

- One product, one monorepo, two backend services, one React application.
- Media Service owns media upload, storage, transcription and media-task reliability.
- Agent Service owns knowledge ingestion, retrieval, analysis, PRD generation, approvals and action items.
- A shared authenticated identity and `tenant_id`/`owner_id` boundary applies end to end. Never reintroduce self-declared role headers as a production path.
- Personal resources are tenant + owner private. Team resources are tenant-shared for authorized members while `owner_id` remains creator/audit attribution.
- Media Service owns Workspace membership and active-Workspace JWT issuance. VIEWER maps to viewer, MEMBER to operator, ADMIN/OWNER to admin; only a server-side membership lookup may change active tenant or role.
- Team writes require a write-capable role and governed approvals keep four-eyes separation. Never let tenant-wide visibility become self-approval authority.
- Every material conclusion must retain evidence. Video evidence includes asset identity and a playable time range.
- Model output is untrusted. Deterministic validation, authorization, idempotency and approval protect side effects.
- Analysis creation ranks evidence by objective only after tenant/owner/asset authorization, then freezes the selected facts with a revision and SHA-256. Confirmation preserves completed stages 1-4 and atomically consumes the resume token with database compare-and-set. Do not silently re-query current evidence or regress to whole-pipeline recomputation.
- Published PRDs are immutable, hash-addressed versions. Derived knowledge remains a candidate until a separate human decision; approval must atomically materialize a managed, retrievable source with candidate/PRD/hash/evidence provenance. Approved knowledge evolves only through audited supersede/revoke requests: never delete historical managed documents, only ACTIVE versions enter future retrieval/graph context, and team requesters cannot approve their own lifecycle request. Derived action items enter the controlled tool approval queue.
- Media processing state and Agent analysis state are separate lifecycles, aggregated only for presentation.
- Media outbox delivery is at-least-once and must be claimed before network I/O: `PENDING -> CLAIMED -> SENT/DEAD`, with conditional owner/lease checks, expiry takeover, bounded retries and downstream idempotency. A `pendingBatch()` read alone is not multi-instance safety evidence.
- Agent Router/Planner/Tool Agent may use provider-compatible structured JSON (`LLM_RESPONSE_FORMAT=auto`: OpenAI strict JSON Schema, DeepSeek JSON Object), but every response remains untrusted and must pass semantic/schema, whitelist, authorization and side-effect checks before use. Unsupported provider features must degrade to rules.

## Grill the user at real decision points

Pause and ask the user when multiple reasonable choices would change product scope, service ownership, identity or tenant semantics, public event contracts, data retention, destructive migration, rollout compatibility, or the release definition. Present the evidence, your recommendation and the tradeoff.

Do not pause for discoverable implementation details, reversible refactors, test fixes or choices already fixed by `knowledge/decisions/`.

## Change workflow

- For a cross-service change, update or add the versioned contract before implementations.
- Keep HTTP handlers thin and domain logic testable without external infrastructure.
- Keep PRD delivery projection in `publication_artifacts.py`; keep governed knowledge materialization and lifecycle transactions in `knowledge_lifecycle_store.py`. Schema changes belong to append-only numbered migrations in `app/schema/`, initialized through `database.init_db()`.
- Keep document/chunk persistence in `database.py` and chat metrics/log/replay behavior in `chat_observability_store.py`. Keep deterministic graph extraction in `graph_extraction.py` and SQLite graph persistence/query in `graph_store.py`.
- Keep ticket and pending-action state in `ticket_store.py`, deterministic ticket rules in `ticket_domain.py`, and authorized graph traversal in `graph_algorithms.py`; keep tool-call audit logs and aggregate tool metrics in `tool_observability_store.py`. Tool policy and execution orchestration remain in `tools.py`.
- Route business dependencies through `app.architecture.*`; only auth, configuration and request/response types are foundation exceptions. Read environment configuration through `config.get_settings()`.
- JSON and SSE chat share `chat_service.py`. Conversation memory supplies topic hints, never historical answers as new evidence; preserve fresh authorized retrieval, lease fencing, call-budget reservations and cancellation cleanup. Only the citation-reviewed `done` response is final.
- Keep `apps/web/src/api.ts` as a compatibility barrel. Add requests to the matching `*Api.ts` domain module and shared transport only to `apiClient.ts`.
- Prefer an end-to-end vertical slice over broad scaffolding with no user-visible path.
- Preserve the light/mock modes, but label them honestly and keep real integration smoke tests separate. The localhost acceptance fixture must use bytes that pass the real media container check; do not weaken production validation to make a test fixture pass.
- Add a regression test for a defect and an evaluation case for a changed Agent behavior.
- Outbox changes must cover competing claimers, expired lease takeover, stale-worker fencing, retry backoff and DEAD transition; structured LLM changes must cover strict-schema/provider compatibility, malformed output and deterministic fallback.
- Analysis/retrieval/checkpoint changes must run the focused workflow tests and `python quality/agent-evals/evaluate_prd.py`; general RAG changes also run V6.
- Conversation, memory, topic-routing or streaming changes must run `test_conversation_stream` and `quality/agent-evals/evaluate_conversation.py`; Web streaming changes also run the browser/parser checks. Use `chatApi.ts` and `hooks/useConversation.ts` for the conversation UI.
- Media outbox, upload or cross-service reliability changes must run the Media integration tests and the localhost acceptance; document whether the result used H2/SQLite/mock or real MySQL/Redis/RocketMQ/S3.
- Approved-knowledge materialization or lifecycle changes must run the focused workflow tests and `python quality/agent-evals/evaluate_knowledge_lifecycle.py`; retrieval visibility changes also run V6.
- Use an ADR for a material architectural decision; do not silently rewrite prior decisions.
- Run the shared lint gates before finishing: `ruff check --config ruff.toml services/agent-service scripts quality` at the repository root and `npm run lint` in `apps/web`. After any `--fix`, rerun the full affected service tests: an automated import cleanup can delete a re-export that other modules still import.
- Evaluation gates must pass in the CI environment (hash embedding, no optional local model, `LLM_ROUTER_ENABLED=0`); a gate that only passes with `fastembed` installed is not evidence.

Read [references/maintenance-workflow.md](references/maintenance-workflow.md) for task routing, verification levels, knowledge ownership and handoff requirements.

When changing retrieval, caching, project knowledge or this Skill, also read [references/semantic-knowledge.md](references/semantic-knowledge.md). Keep the stable Skill prefix short; retrieve dynamic Top-K context after the task is known.

## Knowledge base contract

- Human-maintained truth lives under `knowledge/`.
- `knowledge/generated/CURRENT_STATE.md` is generated; never edit it by hand.
- `knowledge/generated/SEMANTIC_INDEX.json` is a generated routing index, not a fact source; never load its raw vectors into model context or edit it by hand.
- After material code, contract, dependency or test changes, run:

```powershell
python scripts/update_knowledge.py
python scripts/update_knowledge.py --check
```

- CI must run the same `--check` command so stale generated knowledge fails the build.
- Update the relevant human-maintained knowledge page whenever behavior, boundaries, security, operations or acceptance criteria change. The generator cannot infer semantic intent.
- For local-release changes, keep `compose.local.yml`, `docs/LOCAL_RELEASE_RUNBOOK.md`, backup/restore tooling and `scripts/local_acceptance.py` aligned.

## Finish every task

Run focused verification first, then the broader level required by the maintenance reference. Report what passed, what was not runnable, why, and any remaining production boundary.
