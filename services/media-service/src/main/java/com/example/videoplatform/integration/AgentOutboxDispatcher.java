package com.example.videoplatform.integration;

import com.example.videoplatform.workflow.TaskStageLog;
import com.example.videoplatform.workflow.TaskStageLogService;
import java.util.List;
import java.util.UUID;
import java.util.concurrent.atomic.AtomicLong;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.boot.autoconfigure.condition.ConditionalOnProperty;
import org.springframework.scheduling.annotation.Scheduled;
import org.springframework.stereotype.Component;

@Component
@ConditionalOnProperty(prefix = "app.integration.agent", name = "enabled", havingValue = "true")
public class AgentOutboxDispatcher {

	private static final Logger log = LoggerFactory.getLogger(AgentOutboxDispatcher.class);

	private final TranscriptEventOutboxService outboxService;
	private final AgentTranscriptClient client;
	private final TaskStageLogService stageLogs;

	public AgentOutboxDispatcher(TranscriptEventOutboxService outboxService, AgentTranscriptClient client,
			TaskStageLogService stageLogs) {
		this.outboxService = outboxService;
		this.client = client;
		this.stageLogs = stageLogs;
	}

	@Scheduled(fixedDelayString = "${app.integration.agent.dispatch-interval-ms:2000}")
	public void dispatchPending() {
		// Claim immediately before each send; earlier slow requests cannot consume later leases.
		for (int sent = 0; sent < 50 && client.canAttempt(); sent++) {
			List<IntegrationEventOutbox> batch = outboxService.claimBatch(1);
			if (batch.isEmpty()) return;
			IntegrationEventOutbox event = batch.get(0);
			String claimId = event.getClaimId();
			AtomicLong stageId = new AtomicLong();
			try {
				client.send(event.getPayload(), () -> stageId.set(stageLogs.begin(
						event.getAggregateId(), UUID.randomUUID().toString(), TaskStageLog.Stage.DELIVERY)));
				boolean owned = outboxService.markSent(event.getEventId(), claimId);
				finish(stageId.get(), owned ? TaskStageLog.Outcome.SUCCEEDED : TaskStageLog.Outcome.ABANDONED,
						owned ? null : TaskStageLog.ErrorCode.LEASE_LOST);
			} catch (AgentDeliveryCircuit.OpenException exception) {
				outboxService.defer(event.getEventId(), claimId, exception.retryAt());
				return;
			} catch (AgentTranscriptClient.PermanentDeliveryException exception) {
				log.error("Transcript event {} permanently rejected: {}", event.getEventId(), exception.getMessage());
				boolean owned = outboxService.markFailed(event.getEventId(), claimId, exception.getMessage(), true);
				finish(stageId.get(), owned ? TaskStageLog.Outcome.FAILED : TaskStageLog.Outcome.ABANDONED,
						owned ? TaskStageLog.ErrorCode.DELIVERY_REJECTED : TaskStageLog.ErrorCode.LEASE_LOST);
			} catch (Exception exception) {
				log.warn("Transcript event {} delivery failed: {}", event.getEventId(), exception.getMessage());
				boolean owned = outboxService.markFailed(event.getEventId(), claimId, exception.getMessage(), false);
				finish(stageId.get(), owned ? TaskStageLog.Outcome.FAILED : TaskStageLog.Outcome.ABANDONED,
						owned ? TaskStageLog.ErrorCode.DELIVERY_RETRY : TaskStageLog.ErrorCode.LEASE_LOST);
			}
		}
	}

	private void finish(long id, TaskStageLog.Outcome status, TaskStageLog.ErrorCode error) {
		if (id != 0) stageLogs.finish(id, status, error);
	}
}
