package com.example.videoplatform.workflow;

import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.boot.autoconfigure.condition.ConditionalOnProperty;
import org.springframework.scheduling.annotation.Scheduled;
import org.springframework.stereotype.Component;

/** Moves durable task intents onto either the local executor or RocketMQ. */
@Component
@ConditionalOnProperty(prefix = "app.workflow", name = "dispatcher-enabled", havingValue = "true", matchIfMissing = true)
public class WorkflowDispatchDispatcher {

	private static final Logger log = LoggerFactory.getLogger(WorkflowDispatchDispatcher.class);

	private final WorkflowDispatchOutboxService outboxService;
	private final WorkflowPublisher workflowPublisher;

	public WorkflowDispatchDispatcher(WorkflowDispatchOutboxService outboxService,
			WorkflowPublisher workflowPublisher) {
		this.outboxService = outboxService;
		this.workflowPublisher = workflowPublisher;
	}

	@Scheduled(fixedDelayString = "${app.workflow.dispatch-interval-ms:250}")
	public void dispatchPending() {
		for (WorkflowDispatchOutbox event : outboxService.claimBatch()) {
			String claimId = event.getClaimId();
			try {
				workflowPublisher.publish(event.getTaskId());
				if (!outboxService.markSent(event.getTaskId(), claimId)) {
					log.warn("Workflow task {} lost its dispatch lease after publish", event.getTaskId());
				}
			} catch (Exception exception) {
				log.warn("Workflow task {} dispatch deferred: {}", event.getTaskId(), exception.getMessage());
				if (!outboxService.markRetry(event.getTaskId(), claimId, exception.getMessage())) {
					log.warn("Workflow task {} lost its dispatch lease before retry persistence", event.getTaskId());
				}
			}
		}
	}
}
