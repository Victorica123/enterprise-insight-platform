package com.example.videoplatform.workflow;

import com.example.videoplatform.config.AppProperties;
import java.time.Instant;
import java.util.ArrayList;
import java.util.List;
import java.util.UUID;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class WorkflowDispatchOutboxService {

	private final WorkflowDispatchOutboxRepository repository;
	private final AppProperties appProperties;

	public WorkflowDispatchOutboxService(WorkflowDispatchOutboxRepository repository, AppProperties appProperties) {
		this.repository = repository;
		this.appProperties = appProperties;
	}

	/** Joins the caller transaction so task state and dispatch intent commit atomically. */
	@Transactional
	public void enqueue(String taskId) {
		repository.findById(taskId).ifPresentOrElse(
				WorkflowDispatchOutbox::reschedule,
				() -> repository.save(new WorkflowDispatchOutbox(taskId)));
	}

	@Transactional
	public List<WorkflowDispatchOutbox> claimBatch() {
		Instant now = Instant.now();
		Instant claimExpiresAt = now.plusMillis(
				Math.max(100L, appProperties.getWorkflow().getDispatchClaimLeaseMs()));
		List<WorkflowDispatchOutbox> candidates = new ArrayList<>();
		candidates.addAll(repository.findTop50ByStatusAndNextAttemptAtLessThanEqualOrderByCreatedAt(
				WorkflowDispatchOutbox.DispatchStatus.PENDING, now));
		candidates.addAll(repository.findTop50ByStatusAndClaimExpiresAtLessThanEqualOrderByCreatedAt(
				WorkflowDispatchOutbox.DispatchStatus.CLAIMED, now));

		List<WorkflowDispatchOutbox> claimed = new ArrayList<>();
		for (WorkflowDispatchOutbox candidate : candidates) {
			String claimId = UUID.randomUUID().toString();
			if (repository.claimIfAvailable(candidate.getTaskId(),
					WorkflowDispatchOutbox.DispatchStatus.PENDING,
					WorkflowDispatchOutbox.DispatchStatus.CLAIMED,
					now, claimId, claimExpiresAt) == 1) {
				repository.findById(candidate.getTaskId()).ifPresent(claimed::add);
			}
		}
		return claimed;
	}

	@Transactional
	public boolean markSent(String taskId, String claimId) {
		Instant now = Instant.now();
		return repository.markSentIfOwned(taskId,
				WorkflowDispatchOutbox.DispatchStatus.CLAIMED,
				WorkflowDispatchOutbox.DispatchStatus.SENT,
				claimId, now) == 1;
	}

	@Transactional
	public boolean markRetry(String taskId, String claimId, String error) {
		WorkflowDispatchOutbox event = repository.findById(taskId).orElse(null);
		Instant now = Instant.now();
		if (event == null || claimId == null
				|| event.getStatus() != WorkflowDispatchOutbox.DispatchStatus.CLAIMED
				|| !claimId.equals(event.getClaimId())
				|| event.getClaimExpiresAt() == null || !event.getClaimExpiresAt().isAfter(now)) {
			return false;
		}
		int expectedAttempts = event.getAttempts();
		String safeError = truncate(error);
		Instant nextAttemptAt = now.plusMillis(WorkflowDispatchOutbox.retryDelayMillis(expectedAttempts + 1));
		return repository.markRetryIfOwned(taskId,
				WorkflowDispatchOutbox.DispatchStatus.CLAIMED,
				WorkflowDispatchOutbox.DispatchStatus.PENDING,
				claimId, now, expectedAttempts, safeError, nextAttemptAt) == 1;
	}

	private static String truncate(String error) {
		String safe = error == null ? "unknown workflow dispatch failure" : error;
		return safe.length() <= 1000 ? safe : safe.substring(0, 1000) + "... [truncated]";
	}
}
