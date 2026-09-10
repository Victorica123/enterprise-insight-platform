# Service Level Objectives

## Enforced local quality objectives

These objectives are release gates today:

| Signal | Objective | Evidence |
| --- | --- | --- |
| Core localhost workflow | 100% of scripted checks pass | `scripts/local_acceptance.py` |
| Agent regression | 100% test pass | `services/agent-service/tests` |
| Agent golden evaluation | retrieval ≥ 95%, citation ≥ 95%, refusal/security ≥ 95% | `quality/agent-evals/evaluate_v6.py` |
| Tenant isolation | zero cross-tenant/owner positives | negative tests in both services |
| Controlled writes | zero exact-once violations; every side effect has approval audit | tool metrics and approval tests |
| Web release | TypeScript and production build pass | `npm run build` |

## Accepted production-pilot SLO baseline

ADR-0014 activates the following objectives for the limited pilot. They start as measurement targets; localhost tests do not prove compliance:

- authenticated API availability: 99.5% monthly;
- non-model API latency: p95 ≤ 1.5 seconds, p99 ≤ 3 seconds;
- local/fallback Agent answer latency: p95 ≤ 3 seconds; external-provider completion latency is tracked separately;
- transcript-to-searchable-evidence delay: p95 ≤ 5 minutes for supported media sizes;
- accepted outbox event delivery: 99.5% within 60 seconds, zero silent drops;
- evidence integrity: 100% of returned video citations contain accessible tenant-owned asset, segment and valid time range;
- recovery point objective: 24 hours for pilot data; recovery time objective: 2 hours.

Availability excludes declared maintenance. An external model outage is excluded from model-call latency only; the application must still expose stored facts, processing state and approval state through its local/fallback path.

## Measurement and alerting

- Media Service exports health and Micrometer/Prometheus metrics for HTTP, task stages, retries and queue delay.
- Agent Service exposes tenant-scoped chat/tool summaries and auditable logs. Production aggregation must remove tenant identifiers from cross-tenant telemetry views.
- Authenticated Agent embedding status exposes process-local vector and authorized chunk cache occupancy, request count and hit rate. Establish a representative request baseline before defining cache targets; a restarted or cold process is not an SLO breach.
- Page on sustained error-budget burn, dead outbox events, stale media tasks, evidence-validation failures or any exact-once violation.
- Review objectives after at least 14 days of representative pilot traffic; do not tighten targets using only mock localhost timings.
