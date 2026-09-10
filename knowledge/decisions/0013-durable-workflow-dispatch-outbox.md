# ADR 0013: Durable Workflow Dispatch Outbox

- Status: Accepted
- Date: 2026-09-03

## Context

The upload transaction persisted a `QUEUED` video task and then synchronously published it to either the local `@Async` executor or RocketMQ. When the local executor queue was saturated, the API returned 503 after the task and file had already been committed. The caller received no usable task identifier, while a retry could create another task. MQ outages had the same split-commit shape. The stale-task reaper eventually recovered some rows, but its default delay was too long to make the API outcome truthful.

## Decision

Media Service owns a separate internal `workflow_dispatch_outbox` table. Creating, manually retrying, or stale-requeueing a task writes or reactivates its dispatch intent in the same database transaction as the task state transition.

A scheduled dispatcher claims rows with a renewable database lease, publishes the task identifier through the configured `WorkflowPublisher`, and marks the row sent only after the transport accepts it. A rejected executor submission or failed MQ send returns the row to `PENDING` with capped exponential backoff. The existing worker lease and conditional `QUEUED -> TRANSCRIBING` claim remain the processing fence, so duplicate publication is safe.

The public upload and retry response contracts remain unchanged. A successful response now means both the task and a durable dispatch intent were committed; it does not claim that processing has completed.

## Consequences

- Local executor saturation and temporary MQ outages no longer create an HTTP failure after durable task creation.
- Admission throughput can exceed worker throughput, so queue age, active-task quota and end-to-end latency remain required operational signals.
- Delivery is at least once. Worker claims, leases and content single-flight logic must stay idempotent.
- The transcript-ready integration outbox remains separate because it has a different consumer, payload contract and terminal failure policy.
- Hibernate schema update creates the new table in the current delivery model. A future production migration system must convert this implicit schema change into a versioned migration before external rollout.
