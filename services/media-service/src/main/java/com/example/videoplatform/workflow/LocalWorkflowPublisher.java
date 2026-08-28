package com.example.videoplatform.workflow;

import org.springframework.boot.autoconfigure.condition.ConditionalOnProperty;
import org.springframework.stereotype.Component;

@Component
@ConditionalOnProperty(prefix = "app.mq", name = "enabled", havingValue = "false", matchIfMissing = true)
public class LocalWorkflowPublisher implements WorkflowPublisher {

	private final WorkflowProcessor workflowProcessor;

	public LocalWorkflowPublisher(WorkflowProcessor workflowProcessor) {
		this.workflowProcessor = workflowProcessor;
	}

	@Override
	public void publish(String taskId) {
		workflowProcessor.processAsync(taskId);
	}
}
