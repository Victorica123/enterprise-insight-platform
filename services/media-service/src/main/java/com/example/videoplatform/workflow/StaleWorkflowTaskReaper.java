package com.example.videoplatform.workflow;

import com.example.videoplatform.config.AppProperties;
import java.time.Duration;
import java.time.Instant;
import java.util.List;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.boot.autoconfigure.condition.ConditionalOnProperty;
import org.springframework.scheduling.annotation.Scheduled;
import org.springframework.stereotype.Component;

/**
 * 异步任务补偿器：把长时间卡在 QUEUED / TRANSCRIBING / SUMMARIZING 的任务重新投递。
 *
 * <p>它不直接执行视频处理，只负责恢复调度权；真正的幂等仍由
 * {@link VideoTaskService#claimForProcessing(String)} 和内容级单飞保证。
 */
@Component
@ConditionalOnProperty(prefix = "app.workflow", name = "reaper-enabled", havingValue = "true", matchIfMissing = true)
public class StaleWorkflowTaskReaper {

	private static final Logger log = LoggerFactory.getLogger(StaleWorkflowTaskReaper.class);

	private final VideoTaskService videoTaskService;
	private final AppProperties appProperties;
	private final WorkflowMetrics workflowMetrics;

	public StaleWorkflowTaskReaper(VideoTaskService videoTaskService,
			AppProperties appProperties, WorkflowMetrics workflowMetrics) {
		this.videoTaskService = videoTaskService;
		this.appProperties = appProperties;
		this.workflowMetrics = workflowMetrics;
	}

	@Scheduled(
			fixedDelayString = "${app.workflow.reaper-interval-ms:60000}",
			initialDelayString = "${app.workflow.reaper-initial-delay-ms:60000}")
	public void requeueStaleTasks() {
		Duration timeout = appProperties.getWorkflow().getStaleTaskTimeout();
		if (timeout == null || timeout.isZero() || timeout.isNegative()) {
			log.warn("Skip stale workflow task reaper because app.workflow.stale-task-timeout={} is invalid", timeout);
			return;
		}

		Instant cutoff = Instant.now().minus(timeout);
		List<String> taskIds = videoTaskService.requeueStaleTasks(cutoff);
		if (taskIds.isEmpty()) {
			return;
		}

		log.warn("Requeueing {} stale workflow task(s), cutoff={}", taskIds.size(), cutoff);
		for (String taskId : taskIds) {
			workflowMetrics.incrementRequeue("reaper");
		}
	}
}
