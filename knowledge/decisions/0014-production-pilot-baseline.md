# ADR 0014: Production Pilot Baseline

- Status: Accepted
- Date: 2026-09-04

## Context

The localhost workflow proved product behavior with H2, SQLite and local/mock AI, but that path could not validate durable multi-process state, external identity, signing-key separation, model data policy or automatic retention. The user approved a production-pilot baseline before any commercial rollout.

## Decision

1. The production-pilot Compose uses MySQL 8.4 for both backend services, with separate `videoplatform`, `agent_platform` and `keycloak` schemas. Media and Agent continue to own different tables and never join across service boundaries. SQLite remains the zero-dependency development and deterministic acceptance path; `AGENT_REQUIRE_MYSQL=1` makes a pilot misconfiguration fail at startup.
2. Browser authentication uses Keycloak OIDC Authorization Code with PKCE. Media verifies the external issuer, audience, expiry and signature, maps `(issuer, subject)` to an internal user, and creates the personal Workspace idempotently. Local username/password endpoints and UI are disabled in the pilot profile.
3. Media remains the Workspace authorization authority. It signs short-lived active-Workspace tokens with RS256 and publishes only the RSA public material at `/api/auth/jwks`. Agent verifies those tokens through JWKS and still derives tenant, owner, role and workspace type only from signed claims.
4. External transcript, summary and Agent model calls are denied in production unless the signed Workspace tenant appears in `LOCAL_PROD_MODEL_EGRESS_ALLOWED_TENANTS`. A global allow setting cannot bypass the production allowlist. Local/mock processing remains available without data egress.
5. Automatic retention is enabled in the pilot: raw media 30 days, video transcript evidence 180 days and operational/approval audit 365 days. Media deletion is a durable cleanup job; expired transcript caches cannot be reused as ready evidence. Approved knowledge and published business artifacts are not silently removed by this time-based job and remain subject to their governance lifecycle.
6. The pilot SLO is 99.5% monthly authenticated API availability. Non-model API p95 is at most 1.5 seconds, local/fallback Agent response p95 is at most 3 seconds, and transcript-to-searchable-evidence p95 is at most 5 minutes for the declared supported-media envelope. Evidence integrity remains a 100% correctness objective. These are objectives to measure, not claims already achieved by localhost tests.

## Consequences

- Keycloak, RSA key generation/mounting, MySQL schema initialization and retention workers become required pilot components.
- External identity and internal Workspace authorization stay separate, so switching a Workspace still requires Media to re-read membership and sign a new platform token.
- Implementation completion (2026-09-07): the browser renews the five-minute platform session through the IdP refresh grant, then requests the same Workspace from Media using optional `X-Workspace-Id`. Media re-reads membership and role; only a Workspace 404 permits a personal-Workspace fallback. Logout invalidates pending refresh results. This implements the accepted identity boundary without changing the release scope.
- A disabled IdP account can retain access only until the short platform token expires; immediate revocation across all services remains a later enhancement if the pilot requires a smaller window.
- Runtime DDL currently bootstraps Agent tables and Hibernate updates Media tables. A public rollout still requires reviewed versioned migrations and a tested rollback path.
- Real MySQL/Keycloak/provider behavior, soak results and SLO compliance must be collected on a host with Docker and k6. Static checks and H2/SQLite tests do not satisfy those evidence requirements.
