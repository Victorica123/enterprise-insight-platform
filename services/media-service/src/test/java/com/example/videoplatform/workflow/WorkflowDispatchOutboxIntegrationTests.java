package com.example.videoplatform.workflow;

import static org.assertj.core.api.Assertions.assertThat;

import com.example.videoplatform.config.AppProperties;
import java.time.Instant;
import java.util.UUID;
import org.junit.jupiter.api.AfterEach;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;

@SpringBootTest(properties = {
		"app.workflow.dispatcher-enabled=false",
		"spring.datasource.url=jdbc:h2:mem:workflow-dispatch-outbox;DB_CLOSE_DELAY=-1;DB_CLOSE_ON_EXIT=FALSE"
})
class WorkflowDispatchOutboxIntegrationTests {

	@Autowired WorkflowDispatchOutboxService outboxService;
	@Autowired WorkflowDispatchOutboxRepository repository;
	@Autowired AppProperties appProperties;

	@AfterEach
	void restoreLease() {
		appProperties.getWorkflow().setDispatchClaimLeaseMs(30_000);
	}

	@Test
	void onlyLeaseOwnerCanCompleteDispatch() {
		String taskId = "dispatch-" + UUID.randomUUID();
		repository.saveAndFlush(new WorkflowDispatchOutbox(taskId));

		WorkflowDispatchOutbox claimed = claim(taskId);

		assertThat(outboxService.markSent(taskId, "wrong-claim")).isFalse();
		assertThat(outboxService.markSent(taskId, claimed.getClaimId())).isTrue();
		assertThat(outboxService.markSent(taskId, claimed.getClaimId())).isFalse();
		assertThat(repository.findById(taskId).orElseThrow().getStatus())
				.isEqualTo(WorkflowDispatchOutbox.DispatchStatus.SENT);
	}

	@Test
	void failedDispatchReturnsToBoundedBackoff() {
		String taskId = "dispatch-" + UUID.randomUUID();
		repository.saveAndFlush(new WorkflowDispatchOutbox(taskId));
		WorkflowDispatchOutbox claimed = claim(taskId);

		assertThat(outboxService.markRetry(taskId, claimed.getClaimId(), "queue full")).isTrue();
		WorkflowDispatchOutbox retry = repository.findById(taskId).orElseThrow();
		assertThat(retry.getStatus()).isEqualTo(WorkflowDispatchOutbox.DispatchStatus.PENDING);
		assertThat(retry.getAttempts()).isEqualTo(1);
		assertThat(retry.getClaimId()).isNull();
	}

	@Test
	void expiredLeaseCanBeClaimedAgain() throws Exception {
		appProperties.getWorkflow().setDispatchClaimLeaseMs(100);
		String taskId = "dispatch-" + UUID.randomUUID();
		repository.saveAndFlush(new WorkflowDispatchOutbox(taskId));
		WorkflowDispatchOutbox first = claim(taskId);
		Thread.sleep(150);

		WorkflowDispatchOutbox replacement = claim(taskId);

		assertThat(replacement.getClaimId()).isNotEqualTo(first.getClaimId());
		assertThat(outboxService.markSent(taskId, first.getClaimId())).isFalse();
		assertThat(outboxService.markSent(taskId, replacement.getClaimId())).isTrue();
	}

	private WorkflowDispatchOutbox claim(String taskId) {
		return outboxService.claimBatch().stream()
				.filter(candidate -> taskId.equals(candidate.getTaskId()))
				.findFirst().orElseThrow();
	}
}
