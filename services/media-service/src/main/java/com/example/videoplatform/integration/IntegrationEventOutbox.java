package com.example.videoplatform.integration;

import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.EnumType;
import jakarta.persistence.Enumerated;
import jakarta.persistence.Id;
import jakarta.persistence.Index;
import jakarta.persistence.Table;
import java.time.Instant;

@Entity
@Table(name = "integration_event_outbox", indexes = {
		@Index(name = "idx_outbox_status_next_attempt", columnList = "status,nextAttemptAt")
})
public class IntegrationEventOutbox {

	@Id
	private String eventId;

	@Column(nullable = false, length = 100)
	private String eventType;

	@Column(nullable = false, length = 64)
	private String aggregateId;

	@Column(nullable = false, columnDefinition = "TEXT")
	private String payload;

	@Enumerated(EnumType.STRING)
	@Column(nullable = false, length = 20)
	private DeliveryStatus status;

	private int attempts;

	@Column(nullable = false)
	private Instant nextAttemptAt;

	@Column(columnDefinition = "TEXT")
	private String lastError;

	@Column(nullable = false)
	private Instant createdAt;

	private Instant publishedAt;

	protected IntegrationEventOutbox() {
		// JPA
	}

	public IntegrationEventOutbox(String eventId, String eventType, String aggregateId, String payload) {
		this.eventId = eventId;
		this.eventType = eventType;
		this.aggregateId = aggregateId;
		this.payload = payload;
		this.status = DeliveryStatus.PENDING;
		this.createdAt = Instant.now();
		this.nextAttemptAt = this.createdAt;
	}

	public String getEventId() {
		return eventId;
	}

	public String getPayload() {
		return payload;
	}

	public DeliveryStatus getStatus() {
		return status;
	}

	public int getAttempts() {
		return attempts;
	}

	public Instant getNextAttemptAt() {
		return nextAttemptAt;
	}

	public String getLastError() {
		return lastError;
	}

	public void markSent() {
		this.status = DeliveryStatus.SENT;
		this.publishedAt = Instant.now();
		this.lastError = null;
	}

	public void markFailed(String error, int maxAttempts, boolean permanent) {
		this.attempts += 1;
		this.lastError = truncate(error);
		if (permanent || attempts >= Math.max(1, maxAttempts)) {
			this.status = DeliveryStatus.DEAD;
			return;
		}
		long delaySeconds = Math.min(300, 5L * (1L << Math.min(attempts - 1, 6)));
		this.status = DeliveryStatus.PENDING;
		this.nextAttemptAt = Instant.now().plusSeconds(delaySeconds);
	}

	private static String truncate(String value) {
		String safe = value == null ? "unknown delivery failure" : value;
		return safe.length() <= 1000 ? safe : safe.substring(0, 1000) + "... [truncated]";
	}

	public enum DeliveryStatus {
		PENDING,
		SENT,
		DEAD
	}
}
