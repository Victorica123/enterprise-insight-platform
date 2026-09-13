package com.example.videoplatform.workflow;

import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;
import java.time.Instant;
import java.util.List;
import com.example.videoplatform.config.WorkflowProperties;
import java.time.Duration;
import java.util.ArrayList;
import java.util.Optional;
import java.util.UUID;

@Service
public class TaskLeaseService {
	private final VideoTaskRepository taskRepository;
	private final WorkflowProperties properties;
	private final WorkflowDispatchOutboxService workflowDispatchOutboxService;
	private final TaskStageLogService stageLogs;

	public TaskLeaseService(VideoTaskRepository taskRepository, WorkflowProperties properties, WorkflowDispatchOutboxService workflowDispatchOutboxService, TaskStageLogService stageLogs) {
		this.taskRepository = taskRepository;
		this.properties = properties;
		this.workflowDispatchOutboxService = workflowDispatchOutboxService;
		this.stageLogs = stageLogs;
	}

	@Transactional
	public boolean claimForProcessing(String taskId) {
		return claimForProcessingWithLease(taskId).isPresent();
	}

	@Transactional
	public Optional<String> claimForProcessingWithLease(String taskId) {
		Instant now = Instant.now();
		String leaseId = UUID.randomUUID().toString();
		Duration leaseDuration = properties.getTaskLeaseDuration();
		if (leaseDuration == null || leaseDuration.isZero() || leaseDuration.isNegative()) {
			leaseDuration = Duration.ofMinutes(15);
		}
		int updated = taskRepository.claimWithLease(
				taskId, VideoTask.TaskStatus.QUEUED, VideoTask.TaskStatus.TRANSCRIBING,
				leaseId, now.plus(leaseDuration), now);
		return updated > 0 ? Optional.of(leaseId) : Optional.empty();
	}

	@Transactional
	public boolean renewProcessingLease(String taskId, String leaseId) {
		Instant now = Instant.now();
		Duration leaseDuration = properties.getTaskLeaseDuration();
		if (leaseDuration == null || leaseDuration.isZero() || leaseDuration.isNegative()) {
			leaseDuration = Duration.ofMinutes(15);
		}
		return taskRepository.renewLease(
				taskId, leaseId,
				List.of(VideoTask.TaskStatus.TRANSCRIBING, VideoTask.TaskStatus.SUMMARIZING),
				now.plus(leaseDuration), now) > 0;
	}

	public long leaseHeartbeatIntervalMillis() {
		Duration leaseDuration = properties.getTaskLeaseDuration();
		if (leaseDuration == null || leaseDuration.isZero() || leaseDuration.isNegative()) {
			leaseDuration = Duration.ofMinutes(15);
		}
		return Math.max(1000L, leaseDuration.toMillis() / 3);
	}

	@Transactional
	public List<String> requeueStaleTasks(Instant cutoff) {
		List<VideoTask.TaskStatus> retryableStatuses = List.of(
				VideoTask.TaskStatus.QUEUED,
				VideoTask.TaskStatus.TRANSCRIBING,
				VideoTask.TaskStatus.SUMMARIZING);
		List<String> taskIds = new ArrayList<>();
		Instant now = Instant.now();
		for (String taskId : taskRepository.findStaleTaskIds(retryableStatuses, now, cutoff)) {
			if (taskRepository.requeueIfStale(
					taskId, retryableStatuses, VideoTask.TaskStatus.QUEUED, now, cutoff) > 0) {
				stageLogs.abandonProcessing(taskId);
				workflowDispatchOutboxService.enqueue(taskId);
				taskIds.add(taskId);
			}
		}
		return taskIds;
	}
}
