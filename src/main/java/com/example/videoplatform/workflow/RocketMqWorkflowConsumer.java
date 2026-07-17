package com.example.videoplatform.workflow;

import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import org.apache.rocketmq.spring.annotation.RocketMQMessageListener;
import org.apache.rocketmq.spring.core.RocketMQListener;
import org.springframework.boot.autoconfigure.condition.ConditionalOnProperty;
import org.springframework.stereotype.Component;

@Component
@ConditionalOnProperty(prefix = "app.mq", name = "enabled", havingValue = "true")
@RocketMQMessageListener(topic = "video-task", consumerGroup = "video-platform-consumer", nameServer = "${rocketmq.nameServer}")
public class RocketMqWorkflowConsumer implements RocketMQListener<String> {

	private final WorkflowProcessor workflowProcessor;
	private final ObjectMapper objectMapper;

	public RocketMqWorkflowConsumer(WorkflowProcessor workflowProcessor, ObjectMapper objectMapper) {
		this.workflowProcessor = workflowProcessor;
		this.objectMapper = objectMapper;
	}

	@Override
	public void onMessage(String message) {
		try {
			JsonNode root = objectMapper.readTree(message);
			String taskId = root.path("taskId").asText();
			if (taskId == null || taskId.isBlank()) {
				throw new IllegalArgumentException("MQ 消息缺少 taskId: " + message);
			}
			workflowProcessor.process(taskId);
		} catch (Exception e) {
			throw new RuntimeException("MQ 消费失败: " + message, e);
		}
	}
}
