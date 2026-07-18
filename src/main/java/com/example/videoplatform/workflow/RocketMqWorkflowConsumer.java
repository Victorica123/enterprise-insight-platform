package com.example.videoplatform.workflow;

import com.example.videoplatform.config.AppProperties;
import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import org.apache.rocketmq.client.consumer.DefaultMQPushConsumer;
import org.apache.rocketmq.spring.annotation.RocketMQMessageListener;
import org.apache.rocketmq.spring.core.RocketMQListener;
import org.apache.rocketmq.spring.core.RocketMQPushConsumerLifecycleListener;
import org.springframework.boot.autoconfigure.condition.ConditionalOnProperty;
import org.springframework.stereotype.Component;

@Component
@ConditionalOnProperty(prefix = "app.mq", name = "enabled", havingValue = "true")
@RocketMQMessageListener(topic = "video-task", consumerGroup = "video-platform-consumer", nameServer = "${rocketmq.nameServer}")
public class RocketMqWorkflowConsumer
		implements RocketMQListener<String>, RocketMQPushConsumerLifecycleListener {

	private final WorkflowProcessor workflowProcessor;
	private final ObjectMapper objectMapper;
	private final int consumerThreads;

	public RocketMqWorkflowConsumer(WorkflowProcessor workflowProcessor, ObjectMapper objectMapper,
			AppProperties appProperties) {
		this.workflowProcessor = workflowProcessor;
		this.objectMapper = objectMapper;
		this.consumerThreads = Math.max(1, appProperties.getMq().getConsumerThreads());
	}

	@Override
	public void prepareStart(DefaultMQPushConsumer consumer) {
		// 默认与本地 executor max=4 对齐，避免 A/B 时把“更多 worker”误说成“MQ 自带加速”。
		consumer.setConsumeThreadMin(consumerThreads);
		consumer.setConsumeThreadMax(consumerThreads);
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
