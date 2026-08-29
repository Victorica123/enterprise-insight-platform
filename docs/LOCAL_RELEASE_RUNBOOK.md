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

1. registration creates a personal Workspace and trusted JWT;
2. upload, mock transcript, outbox and Agent ingestion complete;
3. video evidence contains an asset, stable segment and time range;
4. analysis waits for missing facts and resumes from confirmation;
5. PRD publication needs two explicit personal-owner steps;
6. publication creates an immutable hash-addressed snapshot;
7. knowledge candidates need a separate human decision;
8. action items only create a pending ticket action, then require approval and project the real ticket ID back;
9. signed playback supports HTTP Range.
10. an OWNER creates a team Workspace and a second registered user consumes a one-time invitation;
11. explicit Workspace switching reissues trusted JWT claims for both members;
12. one member uploads media and the other reads it and retrieves its Agent evidence;
13. the second member's personal Workspace cannot see team resources;
14. team PRD publication rejects self-approval and accepts another write-capable member;
15. team knowledge and ticket delivery remain shared and audited;
16. a freshly switched VIEWER can read shared resources but cannot upload.

## Rollback

Application rollback means checking out the previously accepted Git revision and rebuilding. Data rollback means stopping the local stack and restoring a verified backup. Never overwrite a running H2 database or copy SQLite `-wal` files as a database backup.
