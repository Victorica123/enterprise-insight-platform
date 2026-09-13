# Maintenance workflow

## Knowledge routing

- Product behavior, user journeys, scope: `knowledge/PRODUCT.md`
- Service boundaries and runtime flow: `knowledge/ARCHITECTURE.md`
- Public APIs and events: `knowledge/CONTRACTS.md` plus `contracts/`
- Ownership, tenancy, privacy and approval: `knowledge/DATA_AND_SECURITY.md`
- Agent nodes, prompts, evidence and evaluations: `knowledge/AGENT_ENGINEERING.md`
- Complete framework, data flow, RAG, caching and technical explanation: `knowledge/TECHNICAL_IMPLEMENTATION.md`
- Tests, gates and verified claims: `knowledge/QUALITY.md`
- Local runtime, deployment and incidents: `knowledge/OPERATIONS.md`
- Local release and recovery: `docs/LOCAL_RELEASE_RUNBOOK.md`; objectives: `docs/SLO.md`
- Interview narrative, truthful claims and demo order: `docs/INTERVIEW_GUIDE.md` and `docs/DEMO_SCRIPT.md`
- First-time comprehension, module ownership and symptom routing: `docs/START_HERE.md`
- Accepted architecture choices: `knowledge/decisions/`

## Safe slimming and comprehension

Use behavior-preserving slimming when the repository is hard to navigate but the approved business scope is already complete:

- Measure tracked size and large source files first; optimize cognitive coupling, not line count alone.
- Keep public HTTP/event contracts, security boundaries, ADRs, current golden gates and localhost acceptance evidence.
- Split by a stable reason to change. Preserve a compatibility import/barrel when doing so avoids noisy call-site churn.
- Keep business state separate from observability state: ticket/pending-action persistence belongs in `ticket_store.py`, while tool-call audit and aggregate metrics belong in `tool_observability_store.py`.
- Replace oversized demo binaries with small deterministic fixtures only after every active caller is migrated and the affected gate passes. Git history is the recovery path for removed tracked archives.
- Put the shortest truthful reading route in `docs/START_HERE.md`; keep history under `docs/archive/` and out of the semantic index.
- Do not combine feature removal, contract changes or data-retention changes with a slimming refactor. Those require a separate user decision.

## Verification levels

### Focused

Use for a local defect or isolated refactor. Run the closest unit or component tests and the knowledge drift check.

### Service

Use when a service contract, persistence behavior, authentication, queueing or Agent node changes. Run the complete affected service tests, static/type checks and relevant Agent evaluation gates.

For six-stage analysis, objective retrieval, evidence snapshots or resume behavior, the relevant gates are `tests.test_analysis_workflow` and `quality/agent-evals/evaluate_prd.py`. Also run V6 when shared retriever behavior changes.

For approved-knowledge materialization, supersede/revoke, historical citation state, or managed-document visibility, run `tests.test_analysis_workflow` and `quality/agent-evals/evaluate_knowledge_lifecycle.py`. Run V6 when active-document filtering or shared retrieval changes.

For conversation memory, topic routing, SSE, leases or cumulative budgets, run `tests.test_conversation_stream` and `quality/agent-evals/evaluate_conversation.py`; run V6 when shared evidence selection changes. Browser checks cover follow-up, new conversation, cancellation and Workspace changes; provider-stream unit tests are separate from real external-model acceptance.

### Platform

Use for cross-service contracts, unified authentication, end-to-end workflow, deployment or release work. Run:

- Media Service tests with the supported JDK documented by the repository.
- Agent Service regression tests and relevant evaluation suites.
- Web type check/build and focused UI tests.
- Contract tests plus real JWT personal-owner isolation and team cross-member sharing flows.
- Lightweight end-to-end smoke; real middleware smoke when the change touches it.
- For persistence changes, verify a backup archive checksum/SQLite quick-check and keep restore recoverable.
- Knowledge drift check.

Never reinterpret an unsupported local toolchain failure as an application regression. Record both the supported runtime and the observed failure.

## Contract discipline

- Event names include a version suffix.
- Consumers deduplicate by `event_id` and semantic resource version.
- Breaking fields require a new version; additive optional fields can remain in the current version.
- Events carry `tenant_id`, `owner_id`, `trace_id`, resource identity and occurred time.
- Personal queries use tenant + owner scope; team queries use tenant scope while writes retain creator `owner_id` attribution.
- Active Workspace changes require server-side membership lookup and JWT reissuance; never accept client-selected tenant or role as authority.
- Sensitive storage locations and bearer/playback credentials never enter events or Agent evidence.

## Knowledge update ownership

| Change | Required knowledge update |
| --- | --- |
| Product workflow or acceptance criteria | `PRODUCT.md` |
| Service ownership, queue, database, topology | `ARCHITECTURE.md` and usually an ADR |
| Endpoint, event or shared DTO | `CONTRACTS.md` and machine-readable contract |
| Auth, tenancy, retention, approval | `DATA_AND_SECURITY.md` and usually an ADR |
| Prompt, model routing, evidence policy, tool behavior | `AGENT_ENGINEERING.md` plus evaluation data |
| Approved knowledge approval, supersede/revoke or historical citations | `DATA_AND_SECURITY.md`, `AGENT_ENGINEERING.md`, lifecycle contract and an ADR |
| Embedding, cache, Skill routing or framework explanation | `TECHNICAL_IMPLEMENTATION.md`, `AGENT_ENGINEERING.md` and usually ADR-0007 |
| Tests, metrics or verified claim | `QUALITY.md` |
| Startup, configuration, deployment or recovery | `OPERATIONS.md` |
| Interview claim, demo path or resume boundary | `docs/INTERVIEW_GUIDE.md`, `docs/DEMO_SCRIPT.md` and the supporting quality evidence |

## Handoff checklist

- Explain the user-visible outcome first.
- Link the changed files and contract version.
- State verification results and environmental gaps.
- State whether knowledge generation and `--check` passed.
- Surface the next genuine decision instead of creating speculative infrastructure.
