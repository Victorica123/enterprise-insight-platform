package com.example.videoplatform.integration;

import com.example.videoplatform.config.AppProperties;
import com.example.videoplatform.workflow.VideoTask;
import com.fasterxml.jackson.databind.ObjectMapper;
import java.time.Instant;
import java.util.List;
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

	@Transactional(readOnly = true)
	public List<IntegrationEventOutbox> pendingBatch() {
		return repository.findTop50ByStatusAndNextAttemptAtLessThanEqualOrderByCreatedAt(
				IntegrationEventOutbox.DeliveryStatus.PENDING, Instant.now());
	}

	@Transactional
	public void markSent(String eventId) {
		repository.findById(eventId).ifPresent(IntegrationEventOutbox::markSent);
	}

	@Transactional
	public void markFailed(String eventId, String error, boolean permanent) {
		repository.findById(eventId).ifPresent(event -> event.markFailed(
				error, appProperties.getIntegration().getAgent().getMaxAttempts(), permanent));
	}
}
