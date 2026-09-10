package com.example.videoplatform.workflow;

import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.EnumType;
import jakarta.persistence.Enumerated;
import jakarta.persistence.Id;
import jakarta.persistence.Index;
import jakarta.persistence.Table;
import java.time.Instant;

/** Durable intent to dispatch one persisted video task to the active worker transport. */
@Entity
@Table(name = "workflow_dispatch_outbox", indexes = {
		@Index(name = "idx_workflow_dispatch_pending", columnList = "status,nextAttemptAt"),
		@Index(name = "idx_workflow_dispatch_claim", columnList = "status,claimExpiresAt")
})
public class WorkflowDispatchOutbox {

	@Id
	@Column(length = 64)
	private String taskId;

	@Enumerated(EnumType.STRING)
	@Column(nullable = false, length = 20)
	private DispatchStatus status;

	private int attempts;

	@Column(nullable = false)
	private Instant nextAttemptAt;

	@Column(columnDefinition = "TEXT")
	private String lastError;

	@Column(nullable = false)
	private Instant createdAt;

	private Instant dispatchedAt;

	@Column(length = 64)
	private String claimId;

	private Instant claimExpiresAt;

	protected WorkflowDispatchOutbox() {
		// JPA
	}

	public WorkflowDispatchOutbox(String taskId) {
		this.taskId = taskId;
		this.createdAt = Instant.now();
		reschedule();
	}

	public String getTaskId() {
		return taskId;
	}

	public DispatchStatus getStatus() {
		return status;
	}

	public int getAttempts() {
		return attempts;
	}

	public String getClaimId() {
		return claimId;
	}

	public Instant getClaimExpiresAt() {
		return claimExpiresAt;
	}

	public void reschedule() {
		this.status = DispatchStatus.PENDING;
		this.attempts = 0;
		this.nextAttemptAt = Instant.now();
		this.lastError = null;
		this.dispatchedAt = null;
		this.claimId = null;
		this.claimExpiresAt = null;
	}

	public static long retryDelayMillis(int attemptNumber) {
		long multiplier = 1L << Math.min(Math.max(0, attemptNumber - 1), 5);
		return Math.min(30_000L, 1_000L * multiplier);
	}

	public enum DispatchStatus {
		PENDING,
		CLAIMED,
		SENT
	}
}
