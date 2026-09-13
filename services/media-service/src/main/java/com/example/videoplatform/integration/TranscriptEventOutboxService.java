package com.example.videoplatform.integration;

import com.example.videoplatform.config.AppProperties;
import com.example.videoplatform.workflow.VideoTask;
import com.fasterxml.jackson.databind.ObjectMapper;
import java.time.Instant;
import java.util.ArrayList;
import java.util.List;
import java.util.UUID;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class TranscriptEventOutboxService {

	private final IntegrationEventOutboxRepository repository;
	private final ObjectMapper objectMapper;
	private final AppProperties appProperties;

	public TranscriptEventOutboxService(IntegrationEventOutboxRepository repository, ObjectMapper objectMapper,
			AppProperties appProperties) {
		this.repository = repository;
		this.objectMapper = objectMapper;
		this.appProperties = appProperties;
	}

	/** Called inside the task completion transaction, so completion and event creation commit atomically. */
	public void enqueue(VideoTask task) {
		TranscriptReadyEvent event = TranscriptReadyEvent.from(task, Instant.now());
		if (repository.existsById(event.eventId())) {
			return;
		}
		try {
			String payload = objectMapper.writeValueAsString(event);
			repository.save(new IntegrationEventOutbox(event.eventId(), event.eventType(), task.getTaskId(), payload));
		} catch (Exception exception) {
			throw new IllegalStateException("Unable to create transcript outbox event", exception);
		}
	}

	/**
	 * Atomically claim a bounded batch. A second dispatcher may read the same
	 * candidate list, but only one conditional UPDATE can acquire each lease.
	 */
	@Transactional
	public List<IntegrationEventOutbox> claimBatch() {
		return claimBatch(50);
	}

	@Transactional
	public List<IntegrationEventOutbox> claimBatch(int limit) {
		int boundedLimit = Math.max(1, Math.min(50, limit));
		Instant now = Instant.now();
		Instant leaseExpiresAt = now.plusMillis(
				appProperties.getIntegration().getAgent().getClaimLeaseDurationMs());
		List<IntegrationEventOutbox> candidates = new ArrayList<>();
		candidates.addAll(repository.findTop50ByStatusAndNextAttemptAtLessThanEqualOrderByCreatedAt(
				IntegrationEventOutbox.DeliveryStatus.PENDING, now));
		candidates.addAll(repository.findTop50ByStatusAndClaimExpiresAtLessThanEqualOrderByCreatedAt(
				IntegrationEventOutbox.DeliveryStatus.CLAIMED, now));

		List<IntegrationEventOutbox> claimed = new ArrayList<>();
		for (IntegrationEventOutbox candidate : candidates) {
			if (claimed.size() >= boundedLimit) break;
			String claimId = UUID.randomUUID().toString();
			int updated = repository.claimIfAvailable(
					candidate.getEventId(),
					IntegrationEventOutbox.DeliveryStatus.PENDING,
					IntegrationEventOutbox.DeliveryStatus.CLAIMED,
					now, claimId, leaseExpiresAt);
			if (updated == 1) {
				repository.findById(candidate.getEventId()).ifPresent(claimed::add);
			}
		}
		return claimed;
	}

	/** A circuit skip is not a delivery attempt and must not exhaust the durable retry budget. */
	@Transactional
	public boolean defer(String eventId, String claimId, Instant retryAt) {
		return repository.deferIfOwned(eventId, claimId, Instant.now(), retryAt) == 1;
	}

	@Transactional
	public boolean markSent(String eventId, String claimId) {
		Instant now = Instant.now();
		return repository.markSentIfOwned(
				eventId,
				IntegrationEventOutbox.DeliveryStatus.CLAIMED,
				IntegrationEventOutbox.DeliveryStatus.SENT,
				claimId, now, now) == 1;
	}

	@Transactional
	public boolean markFailed(String eventId, String claimId, String error, boolean permanent) {
		IntegrationEventOutbox event = repository.findById(eventId).orElse(null);
		Instant now = Instant.now();
		if (event == null || claimId == null
				|| event.getStatus() != IntegrationEventOutbox.DeliveryStatus.CLAIMED
				|| !claimId.equals(event.getClaimId())
				|| event.getClaimExpiresAt() == null || !event.getClaimExpiresAt().isAfter(now)) {
			return false;
		}
		int expectedAttempts = event.getAttempts();
		int nextAttempts = expectedAttempts + 1;
		int maxAttempts = Math.max(1, appProperties.getIntegration().getAgent().getMaxAttempts());
		IntegrationEventOutbox.DeliveryStatus nextStatus = permanent || nextAttempts >= maxAttempts
				? IntegrationEventOutbox.DeliveryStatus.DEAD
				: IntegrationEventOutbox.DeliveryStatus.PENDING;
		Instant nextAttemptAt = nextStatus == IntegrationEventOutbox.DeliveryStatus.DEAD
				? now : now.plusSeconds(IntegrationEventOutbox.retryDelaySeconds(nextAttempts));
		String safeError = error == null ? "unknown delivery failure" : error;
		if (safeError.length() > 1000) {
			safeError = safeError.substring(0, 1000) + "... [truncated]";
		}
		return repository.markFailedIfOwned(
				eventId,
				IntegrationEventOutbox.DeliveryStatus.CLAIMED,
				nextStatus,
				claimId, now, expectedAttempts, safeError, nextAttemptAt) == 1;
	}
}
