package com.example.videoplatform.integration;

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

	public AgentOutboxDispatcher(TranscriptEventOutboxService outboxService, AgentTranscriptClient client) {
		this.outboxService = outboxService;
		this.client = client;
	}

	@Scheduled(fixedDelayString = "${app.integration.agent.dispatch-interval-ms:2000}")
	public void dispatchPending() {
		for (IntegrationEventOutbox event : outboxService.claimBatch()) {
			String claimId = event.getClaimId();
			try {
				client.send(event.getPayload());
				if (!outboxService.markSent(event.getEventId(), claimId)) {
					log.warn("Transcript event {} lost its delivery lease before completion", event.getEventId());
				}
			} catch (AgentTranscriptClient.PermanentDeliveryException exception) {
				log.error("Transcript event {} permanently rejected: {}", event.getEventId(), exception.getMessage());
				if (!outboxService.markFailed(event.getEventId(), claimId, exception.getMessage(), true)) {
					log.warn("Transcript event {} lost its delivery lease before failure persistence", event.getEventId());
				}
			} catch (Exception exception) {
				log.warn("Transcript event {} delivery failed: {}", event.getEventId(), exception.getMessage());
				if (!outboxService.markFailed(event.getEventId(), claimId, exception.getMessage(), false)) {
					log.warn("Transcript event {} lost its delivery lease before retry scheduling", event.getEventId());
				}
			}
		}
	}
}
