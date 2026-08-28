---
name: enterprise-insight-maintainer
description: Maintain, review, debug, extend, or release the Enterprise Insight Platform monorepo across its Spring media service, FastAPI agent service, React application, cross-service contracts, project knowledge base, and quality evidence. Use only for this product and its migration sources.
metadata:
  short-description: Maintain the Enterprise Insight Platform
---

# Enterprise Insight Maintainer

Keep this repository a coherent product rather than two demos placed side by side.

## Start every task

1. Resolve the repository root and read `AGENTS.md`.
2. Read `knowledge/INDEX.md`, then load only the references it routes to for the task.
3. Inspect the affected service and its tests before changing code. Treat the original repositories as read-only migration sources.
4. Check the working tree and preserve unrelated user changes.

## Product invariants

- One product, one monorepo, two backend services, one React application.
- Media Service owns media upload, storage, transcription and media-task reliability.
- Agent Service owns knowledge ingestion, retrieval, analysis, PRD generation, approvals and action items.
- A shared authenticated identity and `tenant_id`/`owner_id` boundary applies end to end. Never reintroduce self-declared role headers as a production path.
- Every material conclusion must retain evidence. Video evidence includes asset identity and a playable time range.
- Model output is untrusted. Deterministic validation, authorization, idempotency and approval protect side effects.
- Media processing state and Agent analysis state are separate lifecycles, aggregated only for presentation.

## Grill the user at real decision points

Pause and ask the user when multiple reasonable choices would change product scope, service ownership, identity or tenant semantics, public event contracts, data retention, destructive migration, rollout compatibility, or the release definition. Present the evidence, your recommendation and the tradeoff.

Do not pause for discoverable implementation details, reversible refactors, test fixes or choices already fixed by `knowledge/decisions/`.

## Change workflow

- For a cross-service change, update or add the versioned contract before implementations.
- Keep HTTP handlers thin and domain logic testable without external infrastructure.
- Prefer an end-to-end vertical slice over broad scaffolding with no user-visible path.
- Preserve the light/mock modes, but label them honestly and keep real integration smoke tests separate.
- Add a regression test for a defect and an evaluation case for a changed Agent behavior.
- Use an ADR for a material architectural decision; do not silently rewrite prior decisions.

Read [references/maintenance-workflow.md](references/maintenance-workflow.md) for task routing, verification levels, knowledge ownership and handoff requirements.

## Knowledge base contract

- Human-maintained truth lives under `knowledge/`.
- `knowledge/generated/CURRENT_STATE.md` is generated; never edit it by hand.
- After material code, contract, dependency or test changes, run:

```powershell
python scripts/update_knowledge.py
python scripts/update_knowledge.py --check
```

- CI must run the same `--check` command so stale generated knowledge fails the build.
- Update the relevant human-maintained knowledge page whenever behavior, boundaries, security, operations or acceptance criteria change. The generator cannot infer semantic intent.

## Finish every task

Run focused verification first, then the broader level required by the maintenance reference. Report what passed, what was not runnable, why, and any remaining production boundary.
