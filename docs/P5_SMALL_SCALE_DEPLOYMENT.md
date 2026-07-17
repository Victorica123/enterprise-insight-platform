# P5 Small-Scale Deployment

Goal: make the platform safe enough for a small public trial, with clear controls and a debug path when something fails.

This is not a large production architecture. It is a controlled single-server deployment that lets real users test the product while you keep risk visible.

## Recommended Scope

Use one Linux cloud server first:

- 2-4 vCPU, 8 GB RAM minimum; 4 vCPU, 16 GB RAM is more comfortable for RocketMQ + MySQL + MinIO.
- 80-200 GB disk, depending on video volume.
- Docker + Docker Compose.
- One app domain, for example `video.example.com`.
- One object-storage domain, for example `files.example.com`.
- Nginx or Caddy in front for HTTPS.

For a beginner deployment, the production Compose now includes Caddy. It automatically obtains and renews HTTPS certificates after DNS points both domains to the server.

Do not expose MySQL, Redis, RocketMQ, or raw MinIO ports directly to the public internet.

## What To Expose

Public:

- `443 -> Nginx/Caddy -> app:8081`
- `443 -> Nginx/Caddy -> MinIO API` only through the object-storage domain used by presigned URLs

Private or localhost only:

- MySQL `3306`
- Redis `6379`
- RocketMQ `9876`, `10909`, `10911`
- Prometheus `19090`
- Grafana `13000`
- MinIO console `19001`

Why this matters: most real incidents on small projects are not algorithm problems. They are leaked default passwords, exposed databases, bad object-storage CORS, or logs that do not show where the request broke.

## Files Added For P5

- `Dockerfile`: builds and runs the Spring Boot app with Java 17 and FFmpeg.
- `.dockerignore`: keeps build context small and avoids copying local data.
- `.env.example`: server environment template. Copy to `.env` and replace secrets.
- `docker-compose.prod.yml`: single-server production-like stack.
- `observability/prometheus.prod.yml`: Prometheus config for Docker network scraping.
- `scripts/verify-deploy.ps1`: deployment smoke test.
- `scripts/preflight-deploy.ps1`: validates `.env`, domain mappings, secret lengths, Docker, and Compose before startup.
- `deploy/Caddyfile`: automatic HTTPS reverse proxy; only `/actuator/health` is public, while metrics and Swagger stay private.
- `docs/P5_BEGINNER_LAUNCH_GUIDE.md`: step-by-step Chinese guide for the first public trial.

## First Deployment

On the server:

```bash
git clone <your-repo-url> video-platform
cd video-platform
cp .env.example .env
```

Edit `.env`:

- Change every `CHANGE_ME...` value.
- Set `PUBLIC_APP_DOMAIN=video.example.com`.
- Set `PUBLIC_FILES_DOMAIN=files.example.com`.
- Set `PUBLIC_APP_URL=https://video.example.com`.
- Set `APP_STORAGE_S3_PUBLIC_ENDPOINT=https://files.example.com`.
- Set `MINIO_API_CORS_ALLOW_ORIGIN=https://video.example.com`.
- Keep `APP_TRANSCRIPT_ENABLED=false` and `APP_SUMMARY_ENABLED=false` for the first smoke test.

Run the preflight before startup:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File scripts\preflight-deploy.ps1
```

Fix every `FAIL` result. `WARN` is allowed for the first mock-AI deployment.

Start the core stack:

```bash
docker compose -f docker-compose.prod.yml up -d --build
docker compose -f docker-compose.prod.yml ps
docker compose -f docker-compose.prod.yml logs -f app
```

If image pulling is slow or fails, verify Docker Hub access first:

```bash
docker pull maven:3.9.9-eclipse-temurin-17
docker pull eclipse-temurin:17-jre
```

On servers with unstable Docker Hub access, configure a registry mirror or pre-pull the base images. A failed pull of the base image is a network/registry problem, not an application build failure.

When the app is healthy:

```bash
curl http://127.0.0.1:8081/actuator/health
```

Expected result:

```json
{"status":"UP"}
```

## Nginx Example

App domain:

```nginx
server {
    listen 443 ssl http2;
    server_name video.example.com;

    client_max_body_size 512m;

    location / {
        proxy_pass http://127.0.0.1:8081;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto https;
    }
}
```

Object-storage domain:

```nginx
server {
    listen 443 ssl http2;
    server_name files.example.com;

    client_max_body_size 2g;

    location / {
        proxy_pass http://127.0.0.1:19000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto https;
    }
}
```

Important: `APP_STORAGE_S3_PUBLIC_ENDPOINT` must match the domain that the browser really accesses. S3 presigned URLs include the host in the signature. If the backend signs `http://minio:9000` but the browser opens `https://files.example.com`, direct upload will fail.

## Smoke Verification

From your local machine or the server:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File scripts\verify-deploy.ps1 `
  -BaseUrl "https://video.example.com"
```

What the script verifies:

- app health is `UP`;
- register/login returns JWT;
- normal upload is accepted;
- direct upload init returns a presigned URL;
- browser-style PUT to MinIO succeeds;
- direct upload complete creates a task;
- workflow reaches `COMPLETED`;
- MySQL row exists;
- Redis responds to `PING`;
- MinIO bucket exists.

If the script fails, read the last failed step first. That is the broken boundary.

## Debug Playbook

Start with the boundary, not the whole system.

### 1. App Does Not Open

```bash
docker compose -f docker-compose.prod.yml ps
docker compose -f docker-compose.prod.yml logs --tail=200 app
curl -v http://127.0.0.1:8081/actuator/health
```

Common causes:

- `.env` missing or weak/missing secrets;
- MySQL not healthy;
- app cannot connect to Redis or RocketMQ;
- port not forwarded by Nginx/firewall.

### 2. Login/Register Fails

```bash
docker compose -f docker-compose.prod.yml logs --tail=200 app
docker compose -f docker-compose.prod.yml exec mysql mysql -u"$MYSQL_USERNAME" -p"$MYSQL_PASSWORD" -N -e "SHOW TABLES;" "$MYSQL_DATABASE"
```

Interview point: authentication failure should be separated from persistence failure. The API may show 4xx for bad input, but DB connection problems are backend 5xx and must be debugged from logs.

### 3. Normal Upload Fails

Check:

```bash
docker compose -f docker-compose.prod.yml logs --tail=200 app
df -h
```

Common causes:

- Nginx `client_max_body_size` too small;
- Spring multipart limit too small;
- disk full;
- invalid video extension/content type.

### 4. Direct Upload Fails Before PUT

Check:

```bash
curl -v https://video.example.com/api/media/upload/direct/init
docker compose -f docker-compose.prod.yml logs --tail=200 app
```

Common causes:

- `APP_STORAGE_TYPE` is not `s3`;
- `APP_STORAGE_S3_ENDPOINT` cannot be reached by the app container;
- MinIO credentials do not match.

### 5. Direct Upload PUT Fails

Check browser console and:

```bash
curl -I https://files.example.com/minio/health/live
docker compose -f docker-compose.prod.yml logs --tail=200 minio
```

Common causes:

- `APP_STORAGE_S3_PUBLIC_ENDPOINT` does not match the real browser URL;
- MinIO CORS does not include `MINIO_API_CORS_ALLOW_ORIGIN`;
- Nginx object-storage domain is not proxying to `127.0.0.1:19000`;
- request body limit too small.

### 6. Task Stays QUEUED

Check RocketMQ:

```bash
docker compose -f docker-compose.prod.yml logs --tail=200 rocketmq-namesrv
docker compose -f docker-compose.prod.yml logs --tail=200 rocketmq-broker
docker compose -f docker-compose.prod.yml logs --tail=200 app
```

Common causes:

- app cannot connect to `rocketmq-namesrv:9876`;
- broker advertised address is unreachable;
- consumer throws while processing and message keeps retrying.

Interview point: MQ does not make one video process faster. It protects the upload request path by putting slow processing behind a queue, so traffic spikes become backlog instead of immediate HTTP failures.

### 7. Task Stays TRANSCRIBING Or SUMMARIZING

Check:

```bash
docker compose -f docker-compose.prod.yml logs --tail=300 app
```

Common causes:

- FFmpeg cannot parse the video;
- Whisper/LLM API key is missing or rate limited;
- outbound network blocked;
- large video exceeds timeout.

The stale-task reaper can requeue stuck tasks, and owners can manually retry failed tasks.

### 8. Metrics And Dashboards

Start observability:

```bash
docker compose -f docker-compose.prod.yml --profile observability up -d
```

Open through SSH tunnel:

```bash
ssh -L 13000:127.0.0.1:13000 -L 19090:127.0.0.1:19090 user@server
```

Then:

- Grafana: `http://localhost:13000`
- Prometheus: `http://localhost:19090`

Keep these private unless you add real authentication and IP restrictions.

## Rollback

For a small server, keep rollback simple:

```bash
git log --oneline -5
git checkout <previous-good-commit>
docker compose -f docker-compose.prod.yml up -d --build
docker compose -f docker-compose.prod.yml logs -f app
```

Database rollback is not automatic because the project currently uses Hibernate `ddl-auto=update`, not Flyway/Liquibase migrations. Before real public traffic, add schema migrations and a backup procedure.

## Backup

Minimum:

```bash
docker compose -f docker-compose.prod.yml exec mysql mysqldump -u root -p"$MYSQL_ROOT_PASSWORD" "$MYSQL_DATABASE" > backup.sql
docker run --rm -v video-platform_minio-data:/data -v "$PWD:/backup" alpine tar czf /backup/minio-data.tgz /data
```

For real usage, schedule backups and test restore.

## Launch Checklist

- `.env` secrets replaced.
- JWT secret is random and at least 32 characters.
- MySQL/Redis/RocketMQ ports are not public.
- HTTPS works for app domain.
- HTTPS works for object-storage domain.
- `APP_STORAGE_S3_PUBLIC_ENDPOINT` matches object-storage domain.
- MinIO CORS allows only the app domain.
- `scripts/verify-deploy.ps1` passes.
- A test user can upload, see task status, and see transcript/summary.
- Logs can explain failed upload, failed processing, and failed direct upload.
- Disk usage is monitored.
- Backup command has been tested once.

## Interview Framing

You can explain P5 like this:

> I did not jump straight to Kubernetes. For a small trial I built a single-server Docker deployment with clear service boundaries. The app is public behind Nginx, while MySQL, Redis, RocketMQ, and observability stay private. I added a smoke script that checks the real user path: auth, upload, object-storage PUT, task creation, queue processing, MySQL persistence, Redis, and MinIO. The debug process follows the system boundaries, so when something fails I can locate whether it is auth, app, storage, MQ, DB, or reverse proxy.

Key backend points:

- Configuration externalization: secrets and endpoints live in `.env`, not code.
- Least exposure: internal middleware stays off the public network.
- Object storage: direct upload reduces app-server bandwidth and disk pressure.
- MQ: absorbs processing spikes; it improves request acceptance, not single-task speed.
- Observability: health, logs, Prometheus, Grafana, and a deterministic smoke test.
- Deployment maturity gap: before larger traffic, add Flyway/Liquibase, backups, rate limiting, and CI/CD.
