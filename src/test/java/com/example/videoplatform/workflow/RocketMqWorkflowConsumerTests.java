package com.example.videoplatform.workflow;

import static org.mockito.Mockito.never;
import static org.mockito.Mockito.verify;

import com.example.videoplatform.config.AppProperties;
import com.fasterxml.jackson.databind.ObjectMapper;
import io.micrometer.core.instrument.simple.SimpleMeterRegistry;
import org.apache.rocketmq.client.consumer.DefaultMQPushConsumer;
import org.junit.jupiter.api.Test;

class RocketMqWorkflowConsumerTests {

	private final WorkflowProcessor workflowProcessor = org.mockito.Mockito.mock(WorkflowProcessor.class);
	private final AppProperties appProperties = new AppProperties();
	private final WorkflowMetrics metrics = new WorkflowMetrics(new SimpleMeterRegistry());
	private final RocketMqWorkflowConsumer consumer = new RocketMqWorkflowConsumer(
			workflowProcessor, new ObjectMapper(), appProperties, metrics);

	@Test
	void consumesMessageThroughSynchronousProcessorEntry() {
		consumer.onMessage("{\"taskId\":\"task-1\"}");

		verify(workflowProcessor).process("task-1");
		verify(workflowProcessor, never()).processAsync("task-1");
	}

	@Test
	void malformedMessageIsSkippedWithoutProcessingOrThrowing() {
		// 毒消息：坏载荷不能抛异常（会触发 MQ 重试空转），也不应进入处理流程
		consumer.onMessage("not-a-json{{{");

		verify(workflowProcessor, org.mockito.Mockito.never()).process(org.mockito.ArgumentMatchers.anyString());
	}

	@Test
	void messageMissingTaskIdIsSkippedWithoutProcessing() {
		consumer.onMessage("{\"other\":\"value\"}");

		verify(workflowProcessor, org.mockito.Mockito.never()).process(org.mockito.ArgumentMatchers.anyString());
	}

	@Test
	void configuresConsumerConcurrencyExplicitly() {
		appProperties.getMq().setConsumerThreads(6);
		RocketMqWorkflowConsumer configured = new RocketMqWorkflowConsumer(
				workflowProcessor, new ObjectMapper(), appProperties, metrics);
		DefaultMQPushConsumer pushConsumer = new DefaultMQPushConsumer();

		configured.prepareStart(pushConsumer);

		org.assertj.core.api.Assertions.assertThat(pushConsumer.getConsumeThreadMin()).isEqualTo(6);
		org.assertj.core.api.Assertions.assertThat(pushConsumer.getConsumeThreadMax()).isEqualTo(6);
	}
}
