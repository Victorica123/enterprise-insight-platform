package com.example.videoplatform.integration;

import static org.assertj.core.api.Assertions.assertThat;

import com.example.videoplatform.config.AppProperties;
import java.time.Instant;
import java.util.UUID;
import org.junit.jupiter.api.AfterEach;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;

@SpringBootTest
class OutboxClaimIntegrationTests {

	@Autowired
	private TranscriptEventOutboxService outboxService;

	@Autowired
	private IntegrationEventOutboxRepository repository;

	@Autowired
	private AppProperties appProperties;

	@AfterEach
	void restoreOutboxConfiguration() {
		appProperties.getIntegration().getAgent().setClaimLeaseDurationMs(30_000);
		appProperties.getIntegration().getAgent().setMaxAttempts(10);
	}

	@Test
	void onlyOneDispatcherCanClaimAnAvailableEvent() {
		IntegrationEventOutbox event = newEvent();
		repository.saveAndFlush(event);

		var first = outboxService.claimBatch().stream()
				.filter(candidate -> event.getEventId().equals(candidate.getEventId()))
				.findFirst()
				.orElseThrow();
		var second = outboxService.claimBatch().stream()
				.filter(candidate -> event.getEventId().equals(candidate.getEventId()))
				.findFirst();

		assertThat(first.getStatus()).isEqualTo(IntegrationEventOutbox.DeliveryStatus.CLAIMED);
		assertThat(first.getClaimId()).isNotBlank();
		assertThat(second).isEmpty();
		assertThat(outboxService.markSent(event.getEventId(), first.getClaimId())).isTrue();
		assertThat(outboxService.markSent(event.getEventId(), first.getClaimId())).isFalse();
		assertThat(repository.findById(event.getEventId()).orElseThrow().getStatus())
				.isEqualTo(IntegrationEventOutbox.DeliveryStatus.SENT);
	}

	@Test
	void expiredClaimCanBeTakenOverAndOldWorkerCannotCompleteIt() throws Exception {
		appProperties.getIntegration().getAgent().setClaimLeaseDurationMs(100);
		IntegrationEventOutbox event = newEvent();
		repository.saveAndFlush(event);

		var first = outboxService.claimBatch().stream()
				.filter(candidate -> event.getEventId().equals(candidate.getEventId()))
				.findFirst()
				.orElseThrow();
		Thread.sleep(150);
		var replacement = outboxService.claimBatch().stream()
				.filter(candidate -> event.getEventId().equals(candidate.getEventId()))
				.findFirst()
				.orElseThrow();

		assertThat(replacement.getClaimId()).isNotEqualTo(first.getClaimId());
		assertThat(outboxService.markSent(event.getEventId(), first.getClaimId())).isFalse();
		assertThat(outboxService.markSent(event.getEventId(), replacement.getClaimId())).isTrue();
	}

	@Test
	void failedClaimReturnsToBackoffOrDeadWithoutStaleEntityOverwrite() {
		appProperties.getIntegration().getAgent().setMaxAttempts(3);
		IntegrationEventOutbox event = newEvent();
		repository.saveAndFlush(event);
		var claimed = outboxService.claimBatch().stream()
				.filter(candidate -> event.getEventId().equals(candidate.getEventId()))
				.findFirst()
				.orElseThrow();

		assertThat(outboxService.markFailed(event.getEventId(), claimed.getClaimId(), "temporary failure", false))
				.isTrue();
		IntegrationEventOutbox failed = repository.findById(event.getEventId()).orElseThrow();
		assertThat(failed.getStatus()).isEqualTo(IntegrationEventOutbox.DeliveryStatus.PENDING);
		assertThat(failed.getAttempts()).isEqualTo(1);
		assertThat(failed.getNextAttemptAt()).isAfter(Instant.now());
		assertThat(failed.getClaimId()).isNull();
	}

	private IntegrationEventOutbox newEvent() {
		String eventId = "test-outbox-" + UUID.randomUUID();
		IntegrationEventOutbox event = new IntegrationEventOutbox(eventId, "test.event.v1", "aggregate-1", "{}");
		// Eligibility must not depend on JDBC timestamp rounding or wall-clock resolution.
		org.springframework.test.util.ReflectionTestUtils.setField(event, "nextAttemptAt", Instant.now().minusSeconds(1));
		return event;
	}

	@Test
	void circuitDeferralKeepsRetryBudgetAndChecksLeaseOwnership() {
		IntegrationEventOutbox event = newEvent();
		repository.saveAndFlush(event);
		var claimed = outboxService.claimBatch().stream()
				.filter(candidate -> candidate.getEventId().equals(event.getEventId())).findFirst().orElseThrow();
		Instant retryAt = Instant.now().plusSeconds(30);
		assertThat(outboxService.defer(event.getEventId(), "stale-claim", retryAt)).isFalse();
		assertThat(outboxService.defer(event.getEventId(), claimed.getClaimId(), retryAt)).isTrue();
		var deferred = repository.findById(event.getEventId()).orElseThrow();
		assertThat(deferred.getAttempts()).isZero();
		assertThat(deferred.getStatus()).isEqualTo(IntegrationEventOutbox.DeliveryStatus.PENDING);
		assertThat(deferred.getClaimId()).isNull();
		assertThat(deferred.getNextAttemptAt()).isAfter(Instant.now());
	}
}
