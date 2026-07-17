package com.example.videoplatform.workflow;

import static org.mockito.Mockito.never;
import static org.mockito.Mockito.verify;

import com.fasterxml.jackson.databind.ObjectMapper;
import org.junit.jupiter.api.Test;

class RocketMqWorkflowConsumerTests {

	private final WorkflowProcessor workflowProcessor = org.mockito.Mockito.mock(WorkflowProcessor.class);
	private final RocketMqWorkflowConsumer consumer = new RocketMqWorkflowConsumer(
			workflowProcessor, new ObjectMapper());

	@Test
	void consumesMessageThroughSynchronousProcessorEntry() {
		consumer.onMessage("{\"taskId\":\"task-1\"}");

		verify(workflowProcessor).process("task-1");
		verify(workflowProcessor, never()).processAsync("task-1");
	}
}
