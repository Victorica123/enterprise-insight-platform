package com.example.videoplatform.workflow;

import com.fasterxml.jackson.databind.ObjectMapper;
import java.nio.charset.StandardCharsets;
import org.apache.rocketmq.spring.core.RocketMQTemplate;
import org.springframework.boot.autoconfigure.condition.ConditionalOnProperty;
import org.springframework.messaging.support.MessageBuilder;
import org.springframework.stereotype.Component;

@Component
@ConditionalOnProperty(prefix = "app.mq", name = "enabled", havingValue = "true")
public class RocketMqWorkflowPublisher implements WorkflowPublisher {

	private static final String TOPIC = "video-task";

	private final RocketMQTemplate rocketMQTemplate;
	private final ObjectMapper objectMapper;

	public RocketMqWorkflowPublisher(RocketMQTemplate rocketMQTemplate, ObjectMapper objectMapper) {
		this.rocketMQTemplate = rocketMQTemplate;
		this.objectMapper = objectMapper;
	}

	@Override
	public void publish(String taskId) {
		try {
			String payload = objectMapper.writeValueAsString(java.util.Map.of("taskId", taskId));
			rocketMQTemplate.syncSend(TOPIC, MessageBuilder.withPayload(payload.getBytes(StandardCharsets.UTF_8)).build());
		} catch (Exception e) {
			throw new IllegalStateException("RocketMQ 消息发送失败", e);
		}
	}
}
