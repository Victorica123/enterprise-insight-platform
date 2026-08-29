# ADR 0005: Published PRD versions and governed derived deliverables

- Status: Accepted
- Date: 2026-08-29

## Context

PRD publication previously changed a mutable session JSON field to `PUBLISHED`, but did not create a durable product version or the next business artifacts. Automatically merging generated claims into knowledge or immediately creating tickets would violate the evidence and human-approval boundaries.

## Decision

When the publication compare-and-set succeeds, Agent Service writes all of the following in the same SQLite transaction as the approval audit:

1. an immutable PRD version with canonical SHA-256 content identity;
2. one evidence-preserving knowledge candidate per published requirement, initially `PENDING`;
3. one internal action-item draft per requirement, initially `DRAFT`.

Knowledge candidates require another explicit decision. A personal Workspace owner may decide its candidate; a team candidate requires a different write-capable member from the session owner. Action items cannot create tickets directly: the owner may only create an idempotent pending tool action, which then follows the normal Workspace approval policy and audit. The terminal tool result is projected back as `TICKET_CREATED`, `TICKET_REJECTED` or `TICKET_FAILED`; a successful projection retains the real `ticket_id`, and a repeated entry request reuses the original action.

Published versions are append-only. Future PRD changes create a new version; they never overwrite the payload or hash of an accepted version.

## Consequences

- PRD, knowledge and execution are separate governed states instead of one overloaded publication flag.
- Every derived fact and action retains requirement identity and evidence references.
- A publication transaction cannot succeed without its immutable version and initial derived artifacts.
- Team membership creation and Workspace switching remain a separate identity decision; this ADR only governs actors already represented by trusted Workspace claims.
