# Local Release Runbook

This runbook is the supported release path for a reviewer who has no server, domain, cloud storage or model account.

## Prerequisites

- Path A, zero-container acceptance: Python 3.12, JDK 17/18 and Maven.
- Path B, persistent local workspace: Docker Engine with Compose v2.
- Node.js 22 is only required when rebuilding the Web outside Docker.

## Release gate

Run from the repository root:

Run the Agent suite inside `services/agent-service`:

```powershell
python -m unittest discover -s tests -q
```

Then run from the repository root:

```powershell
python quality/agent-evals/evaluate_v6.py
cd apps/web
npm ci
npm run build
cd ../..
python scripts/local_acceptance.py
python scripts/update_knowledge.py
python scripts/update_knowledge.py --check
```

Media Service must additionally pass `mvn -q test` on JDK 17/18. A failure caused only by running Mockito/ByteBuddy on unsupported JDK 25 is not a valid product regression result and is not a pass.

## Persistent localhost workspace

```powershell
./scripts/start_local.ps1 -Build
```

Open `http://127.0.0.1:8080`. The browser uses one origin; nginx routes `/agent/*` to FastAPI and `/media/*` to Spring Boot. Data is stored under the ignored `runtime/` directory:

- `runtime/agent/knowledge_base.sqlite3`
- `runtime/media/db/`
- `runtime/media/storage/`

The Compose profile uses local H2, SQLite, mock transcription and local Agent responses. It is not evidence for Redis, RocketMQ, MySQL, S3 or an external model.

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

## Rollback

Application rollback means checking out the previously accepted Git revision and rebuilding. Data rollback means stopping the local stack and restoring a verified backup. Never overwrite a running H2 database or copy SQLite `-wal` files as a database backup.
