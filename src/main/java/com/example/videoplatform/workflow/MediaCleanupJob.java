package com.example.videoplatform.workflow;

import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.Id;
import jakarta.persistence.Table;
import java.time.Duration;
import java.time.Instant;
import java.util.UUID;

/** Durable outbox row for deleting media after the owning task transaction commits. */
@Entity
@Table(name = "media_cleanup_job")
public class MediaCleanupJob {

	@Id
	private String jobId;

	@Column(nullable = false, length = 512)
	private String storagePath;

	private int attemptCount;

	@Column(columnDefinition = "TEXT")
	private String lastError;

	private Instant nextAttemptAt;
	private Instant createdAt;
	private Instant updatedAt;

	protected MediaCleanupJob() {
		// JPA
	}

	public MediaCleanupJob(String storagePath) {
		this.jobId = UUID.randomUUID().toString();
		this.storagePath = storagePath;
		this.nextAttemptAt = Instant.now();
		this.createdAt = this.nextAttemptAt;
		this.updatedAt = this.nextAttemptAt;
	}

	public String getJobId() {
		return jobId;
	}

	public String getStoragePath() {
		return storagePath;
	}

	public int getAttemptCount() {
		return attemptCount;
	}

	public String getLastError() {
		return lastError;
	}

	public Instant getNextAttemptAt() {
		return nextAttemptAt;
	}

	public Instant getCreatedAt() {
		return createdAt;
	}

	public Instant getUpdatedAt() {
		return updatedAt;
	}

	public void recordFailure(String error, Duration retryDelay) {
		this.attemptCount++;
		this.lastError = error;
		this.nextAttemptAt = Instant.now().plus(retryDelay);
		this.updatedAt = Instant.now();
	}
}
