package com.example.videoplatform.workflow;

import com.example.videoplatform.config.AppProperties;
import com.fasterxml.jackson.databind.ObjectMapper;
import org.apache.rocketmq.client.consumer.DefaultMQPushConsumer;
import org.apache.rocketmq.spring.annotation.RocketMQMessageListener;
import org.apache.rocketmq.spring.core.RocketMQListener;
import org.apache.rocketmq.spring.core.RocketMQPushConsumerLifecycleListener;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.boot.autoconfigure.condition.ConditionalOnProperty;
import org.springframework.stereotype.Component;

@Component
@ConditionalOnProperty(prefix = "app.mq", name = "enabled", havingValue = "true")
@RocketMQMessageListener(topic = "video-task", consumerGroup = "video-platform-consumer", nameServer = "${rocketmq.nameServer}")
public class RocketMqWorkflowConsumer
		implements RocketMQListener<String>, RocketMQPushConsumerLifecycleListener {

	private static final Logger log = LoggerFactory.getLogger(RocketMqWorkflowConsumer.class);

	private final WorkflowProcessor workflowProcessor;
	private final ObjectMapper objectMapper;
	private final int consumerThreads;
	private final WorkflowMetrics metrics;

	public RocketMqWorkflowConsumer(WorkflowProcessor workflowProcessor, ObjectMapper objectMapper,
			AppProperties appProperties, WorkflowMetrics metrics) {
		this.workflowProcessor = workflowProcessor;
		this.objectMapper = objectMapper;
		this.consumerThreads = Math.max(1, appProperties.getMq().getConsumerThreads());
		this.metrics = metrics;
	}

	@Override
	public void prepareStart(DefaultMQPushConsumer consumer) {
		// 默认与本地 executor max=4 对齐，避免 A/B 时把“更多 worker”误说成“MQ 自带加速”。
		consumer.setConsumeThreadMin(consumerThreads);
		consumer.setConsumeThreadMax(consumerThreads);
	}

	@Override
	public void onMessage(String message) {
		String taskId;
		try {
			taskId = objectMapper.readTree(message).path("taskId").asText();
		} catch (Exception parseError) {
			// 毒消息：重试无法修复坏载荷。记录指标与原文后正常返回（ACK 跳过），
			// 避免空转 16 次重试才进死信队列。
			metrics.incrementSkip("mq_poison_message");
			log.error("MQ 消息无法解析，已跳过: {}", message, parseError);
			return;
		}
		if (taskId == null || taskId.isBlank()) {
			metrics.incrementSkip("mq_poison_message");
			log.error("MQ 消息缺少 taskId，已跳过: {}", message);
			return;
		}
		// 处理阶段异常继续向上抛：交给 MQ 重试 + stale-task reaper 补偿
		workflowProcessor.process(taskId);
	}
}
