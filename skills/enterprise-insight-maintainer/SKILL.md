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
2. Read `knowledge/INDEX.md`, then load only the references it routes to for the task.
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
- Published PRDs are immutable, hash-addressed versions. Derived knowledge remains a candidate until a separate human decision; approval must atomically materialize a managed, retrievable knowledge source with candidate/PRD/hash/evidence provenance. Ordinary document deletion cannot bypass this governance. Derived action items enter the controlled tool approval queue.
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
