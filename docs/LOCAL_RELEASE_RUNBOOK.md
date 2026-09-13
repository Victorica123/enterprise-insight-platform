# Local Release Runbook

This runbook is the supported release path for a reviewer who has no server, domain, cloud storage or model account.

## Prerequisites

- Path A, zero-container acceptance: Python 3.12, JDK 17/18 and Maven.
- Path B, persistent local workspace: Docker Engine with Compose v2.
- Path C, production-like reliability lab: Docker Engine with Compose v2 and k6.
- Node.js 22 is only required when rebuilding the Web outside Docker.

## Release gate

Run from the repository root:

Run the Agent suite inside `services/agent-service`:

```powershell
$env:LLM_ROUTER_ENABLED = '0'
python -m unittest discover -s tests -q
```

Then run from the repository root:

```powershell
uvx ruff@0.16.6 check --config ruff.toml services/agent-service scripts quality
python quality/agent-evals/evaluate_v6.py
python quality/agent-evals/evaluate_prd.py
python quality/agent-evals/evaluate_knowledge_lifecycle.py
python quality/agent-evals/evaluate_conversation.py
python quality/agent-evals/evaluate_v5.py
cd apps/web
npm ci
npm run lint
npm test
npm run build
cd ../..
python scripts/local_acceptance.py
python scripts/update_knowledge.py
python scripts/update_knowledge.py --check
```

Media Service must additionally pass `mvn -q test` on JDK 17/18. A failure caused only by running Mockito/ByteBuddy on unsupported JDK 25 is not a valid product regression result and is not a pass.

Use hash embeddings and `LLM_ROUTER_ENABLED=0` for the evaluation gates. `quality/agent-evals/context-harness.ps1 -Mode verify` runs the Agent, Web and maintenance gates with those overrides, prefers the repository virtualenv, and restores environment variables on exit. Media tests, localhost acceptance and backup/restore remain separate platform gates.

The Agent container starts with `python -m app.serve`, defaults to one worker, and validates typed settings before startup. `LOCAL_AGENT_WORKERS` and `LOCAL_AGENT_THREAD_POOL_SIZE` configure the light Compose; each worker owns its model/cache memory. Eight append-only migrations and a ledger serialize SQLite/MySQL initialization; m008 widens seven MySQL evidence/lifecycle columns to LONGTEXT. MySQL 8.4 new/legacy databases, concurrent Agent startup and database restore passed in an isolated lab on 2026-09-13. Repeat the drill with a copy of the target data before upgrading; vector JSON compatibility does not guarantee whole-schema downgrades. See ADR-0017/0018 and `knowledge/QUALITY.md`.

## Media schema upgrade

Media now uses Flyway V1/V2 for H2 and MySQL; Hibernate only validates the resulting schema. Empty databases migrate automatically. For a legacy database without Flyway history:

1. Stop writers, create and verify a backup, then rehearse against an isolated copy with the matching application configuration.
2. Set `MEDIA_FLYWAY_BASELINE_ON_MIGRATE=true` only for that verified legacy upgrade. Both Compose files pass this variable to Media. The application checks the frozen V1 tables, columns, primary keys and unique constraints before registering V1 and applying V2.
3. Verify history, retained business rows and restart behavior, then return the variable to false. Repeat the approved procedure for the target deployment with its own backup.

Do not use `ddl-auto=update`, clean, manual history edits or automatic repair to bypass a failure. Unknown future versions prevent startup. Task-stage logging follows the existing audit retention period; hard-crashed DELIVERY log rows may remain RUNNING even after the outbox is recovered, so inspect both records during incident diagnosis.

## Persistent localhost workspace

```powershell
./scripts/start_local.ps1 -Build
```

Open `http://127.0.0.1:8080`. The browser uses one origin; nginx routes `/agent/*` to FastAPI and `/media/*` to Spring Boot. Data is stored under the ignored `runtime/` directory:

- `runtime/agent/knowledge_base.sqlite3`
- `runtime/media/db/`
- `runtime/media/storage/`

The Compose profile uses local H2, SQLite, mock transcription and local Agent responses. It is not evidence for Redis, RocketMQ, MySQL, S3 or an external model.

## Production-like localhost reliability lab

For real MySQL, Redis, RocketMQ and MinIO integration, concurrent soak, JFR/thread/heap diagnostics and optional Toxiproxy fault injection, use `docs/LOCAL_RELIABILITY_RUNBOOK.md`. This still runs entirely on the development machine and deliberately keeps external AI providers optional.

## Backup and restore drill

Stop the stack before copying H2:

```powershell
./scripts/stop_local.ps1
python scripts/local_data.py backup
python scripts/local_data.py verify backups/local-YYYYMMDD-HHMMSS.zip
python scripts/local_data.py restore backups/local-YYYYMMDD-HHMMSS.zip --force
./scripts/start_local.ps1
```

Restore verifies every SHA-256 checksum and SQLite `quick_check`. If existing runtime data is replaced, an automatic `backups/pre-restore-*.zip` is created first.

`local_data.py` covers the light runtime files, not MySQL/MinIO named volumes. The 2026-09-13 isolated lab separately stopped its application writers, dumped both MySQL business databases, verified a ZIP/SHA-256 manifest, restored into new schemas and compared every table's row count and content digest: 33 tables / 518 rows matched. Evidence and the local archive path are in `knowledge/QUALITY.md`. This does not establish MinIO, Keycloak or cross-host recovery.

## Functional acceptance checklist

The automated localhost runner verifies:

1. registration creates a personal Workspace;
2. the issued JWT contains the trusted tenant identity;
3. a media upload creates a durable task;
4. local mock transcription completes without an external model;
5. the transactional outbox delivers evidence to Agent Service;
6. Agent retrieval can answer from the ingested evidence;
7. video evidence contains a stable segment and time range;
8. analysis waits for missing facts and resumes from confirmation;
9. the resumed analysis generates an evidence-backed PRD;
10. PRD publication requires explicit approval and records audit actors;
11. publication creates an immutable hash-addressed snapshot;
12. knowledge candidates require a separate human decision;
13. action items require tool approval and project the real ticket ID back;
14. signed playback supports HTTP Range;
15. a second user joins a team through a one-time invitation and both users switch explicitly;
16. one team member can read another member's media;
17. the second member's personal Workspace cannot see team resources;
18. the second team member retrieves shared Agent evidence;
19. team publication rejects self-approval and accepts another write-capable member;
20. team knowledge and ticket delivery remain shared and audited;
21. a freshly switched VIEWER can read shared resources but cannot upload;
22. anonymous cache metrics are rejected and public status does not expose cache traffic;
23. authenticated retrieval exposes scope-safe Chunk cache metrics;
24. an approved candidate materializes a managed knowledge document with PRD/candidate/hash provenance;
25. future RAG retrieves that approved knowledge and returns matching provenance.
26. analysis exposes an objective-ranked hybrid evidence snapshot with revision and SHA-256;
27. confirmation increments the checkpoint while preserving stages 1-4 and the frozen evidence fingerprint;
28. reusing the consumed resume token returns HTTP 409.
29. approved knowledge supersession creates an immutable predecessor/successor chain;
30. revocation removes the current knowledge from future retrieval without deleting history;
31. a historical chat replay preserves its original citation and reports the current lifecycle status;
32. lifecycle requests require a separate explicit decision;
33. a team lifecycle requester cannot approve the same request, while another write member can.
34. SSE ends with a verified response retaining video time evidence;
35. completed conversations persist within the authorized Workspace;
36. a follow-up reuses topic hints while retrieving evidence again.
37. stage records satisfy the contract and reflect only executed processing and delivery;
38. exclusive stage cursors paginate without duplication;
39. anonymous and cross-owner stage access is rejected;
40. authorized teammates can read shared task stages;
41. VIEWER can read stages while media writes remain forbidden;
42. populated chat metrics aggregate successfully on both SQLite and MySQL.

## Rollback

Application rollback requires a schema version supported by that application. When the old application rejects a newer migration ledger, stop writers and restore the matching verified pre-upgrade backup into a recoverable target before switching. Keep the current data available for recovery and review any writes since the backup. Never overwrite a running H2 database or copy SQLite `-wal` files as a database backup.
