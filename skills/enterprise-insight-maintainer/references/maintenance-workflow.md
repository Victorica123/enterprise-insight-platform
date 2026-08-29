# Maintenance workflow

## Knowledge routing

- Product behavior, user journeys, scope: `knowledge/PRODUCT.md`
- Service boundaries and runtime flow: `knowledge/ARCHITECTURE.md`
- Public APIs and events: `knowledge/CONTRACTS.md` plus `contracts/`
- Ownership, tenancy, privacy and approval: `knowledge/DATA_AND_SECURITY.md`
- Agent nodes, prompts, evidence and evaluations: `knowledge/AGENT_ENGINEERING.md`
- Tests, gates and verified claims: `knowledge/QUALITY.md`
- Local runtime, deployment and incidents: `knowledge/OPERATIONS.md`
- Local release and recovery: `docs/LOCAL_RELEASE_RUNBOOK.md`; objectives: `docs/SLO.md`
- Local release and recovery: `docs/LOCAL_RELEASE_RUNBOOK.md`; objectives: `docs/SLO.md`
- Accepted architecture choices: `knowledge/decisions/`

## Verification levels

### Focused

Use for a local defect or isolated refactor. Run the closest unit or component tests and the knowledge drift check.

### Service

Use when a service contract, persistence behavior, authentication, queueing or Agent node changes. Run the complete affected service tests, static/type checks and relevant Agent evaluation gates.

### Platform

Use for cross-service contracts, unified authentication, end-to-end workflow, deployment or release work. Run:

- Media Service tests with the supported JDK documented by the repository.
- Agent Service regression tests and relevant evaluation suites.
- Web type check/build and focused UI tests.
- Contract tests and a real JWT owner-isolation flow.
- Lightweight end-to-end smoke; real middleware smoke when the change touches it.
- For persistence changes, verify a backup archive checksum/SQLite quick-check and keep restore recoverable.
- For persistence changes, verify a backup archive checksum/SQLite quick-check and keep restore recoverable.
- Knowledge drift check.

Never reinterpret an unsupported local toolchain failure as an application regression. Record both the supported runtime and the observed failure.

## Contract discipline

- Event names include a version suffix.
- Consumers deduplicate by `event_id` and semantic resource version.
- Breaking fields require a new version; additive optional fields can remain in the current version.
- Events carry `tenant_id`, `owner_id`, `trace_id`, resource identity and occurred time.
- Sensitive storage locations and bearer/playback credentials never enter events or Agent evidence.

## Knowledge update ownership

| Change | Required knowledge update |
| --- | --- |
| Product workflow or acceptance criteria | `PRODUCT.md` |
| Service ownership, queue, database, topology | `ARCHITECTURE.md` and usually an ADR |
| Endpoint, event or shared DTO | `CONTRACTS.md` and machine-readable contract |
| Auth, tenancy, retention, approval | `DATA_AND_SECURITY.md` and usually an ADR |
| Prompt, model routing, evidence policy, tool behavior | `AGENT_ENGINEERING.md` plus evaluation data |
| Tests, metrics or verified claim | `QUALITY.md` |
| Startup, configuration, deployment or recovery | `OPERATIONS.md` |

## Handoff checklist

- Explain the user-visible outcome first.
- Link the changed files and contract version.
- State verification results and environmental gaps.
- State whether knowledge generation and `--check` passed.
- Surface the next genuine decision instead of creating speculative infrastructure.
