package com.example.videoplatform.workflow;

import com.example.videoplatform.media.MediaStorageService;
import io.micrometer.core.instrument.MeterRegistry;
import java.io.IOException;
import java.time.Duration;
import java.time.Instant;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.scheduling.annotation.Scheduled;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class MediaLifecycleService {

	private static final Logger log = LoggerFactory.getLogger(MediaLifecycleService.class);
	private static final int MAX_ERROR_LENGTH = 1000;

	private final VideoTaskRepository taskRepository;
	private final WorkflowDispatchOutboxRepository workflowDispatchOutboxRepository;
	private final MediaCleanupJobRepository cleanupJobRepository;
	private final MediaStorageService mediaStorageService;
	private final MeterRegistry meterRegistry;

	public MediaLifecycleService(VideoTaskRepository taskRepository,
			WorkflowDispatchOutboxRepository workflowDispatchOutboxRepository,
			MediaCleanupJobRepository cleanupJobRepository,
			MediaStorageService mediaStorageService,
			MeterRegistry meterRegistry) {
		this.taskRepository = taskRepository;
		this.workflowDispatchOutboxRepository = workflowDispatchOutboxRepository;
		this.cleanupJobRepository = cleanupJobRepository;
		this.mediaStorageService = mediaStorageService;
		this.meterRegistry = meterRegistry;
	}

	/**
	 * Deletes only a terminal owner-scoped task and records storage cleanup in the same short transaction.
	 * The controller calls {@link #attemptCleanup(DeletionPlan)} after this transaction commits.
	 */
	@Transactional
	public DeletionPlan scheduleTaskDeletion(String taskId, String owner) {
		VideoTask task = taskRepository.findByTaskIdAndOwner(taskId, owner)
				.orElseThrow(() -> new IllegalArgumentException("任务不存在或无权限: " + taskId));
		if (task.getStatus() != VideoTask.TaskStatus.COMPLETED
				&& task.getStatus() != VideoTask.TaskStatus.FAILED) {
			throw new IllegalArgumentException("任务处理中，完成或失败后才能删除: " + taskId);
		}

		String storagePath = task.getStoragePath();
		workflowDispatchOutboxRepository.deleteById(taskId);
		taskRepository.delete(task);
		taskRepository.flush();
		if (storagePath == null || storagePath.isBlank()) {
			return new DeletionPlan(taskId, null, "NO_MEDIA");
		}

		// Always enqueue. Concurrent deletion of the last two references must not let both transactions
		// observe the other uncommitted row and skip cleanup. Duplicate storage DELETE operations are idempotent.
		MediaCleanupJob job = cleanupJobRepository.save(new MediaCleanupJob(storagePath));
		return new DeletionPlan(taskId, job.getJobId(), "PENDING");
	}

	/** Performs storage I/O outside the task deletion transaction and leaves a durable retry row on failure. */
	public WorkflowDtos.TaskDeletionView attemptCleanup(DeletionPlan plan) {
		if (plan.cleanupJobId() == null) {
			return new WorkflowDtos.TaskDeletionView(plan.taskId(), plan.initialStatus());
		}
		return attemptCleanup(plan.taskId(), plan.cleanupJobId());
	}

	@Scheduled(fixedDelayString = "${app.storage.cleanup.retry-interval-ms:60000}")
	public void retryPendingCleanup() {
		for (MediaCleanupJob job : cleanupJobRepository
				.findTop50ByNextAttemptAtBeforeOrderByCreatedAtAsc(Instant.now())) {
			attemptCleanup(null, job.getJobId());
		}
	}

	private WorkflowDtos.TaskDeletionView attemptCleanup(String taskId, String cleanupJobId) {
		MediaCleanupJob job = cleanupJobRepository.findById(cleanupJobId).orElse(null);
		if (job == null) {
			return new WorkflowDtos.TaskDeletionView(taskId, "DELETED");
		}

		String storagePath = job.getStoragePath();
		if (taskRepository.existsByStoragePath(storagePath)) {
			cleanupJobRepository.deleteById(cleanupJobId);
			incrementCleanup("retained_shared");
			return new WorkflowDtos.TaskDeletionView(taskId, "RETAINED_SHARED");
		}

		try {
			mediaStorageService.delete(storagePath);
			cleanupJobRepository.deleteById(cleanupJobId);
			incrementCleanup("deleted");
			return new WorkflowDtos.TaskDeletionView(taskId, "DELETED");
		} catch (IOException | RuntimeException exception) {
			Duration retryDelay = Duration.ofSeconds(Math.min(3600, 1L << Math.min(job.getAttemptCount() + 1, 11)));
			job.recordFailure(truncate(exception.getMessage()), retryDelay);
			cleanupJobRepository.save(job);
			incrementCleanup("retry_pending");
			log.warn("Media cleanup {} failed on attempt {}; retry scheduled: {}",
					cleanupJobId, job.getAttemptCount(), exception.getMessage());
			return new WorkflowDtos.TaskDeletionView(taskId, "RETRY_PENDING");
		}
	}

	private void incrementCleanup(String result) {
		meterRegistry.counter("video.media.cleanup", "result", result).increment();
	}

	private static String truncate(String message) {
		if (message == null) {
			return "unknown cleanup error";
		}
		return message.length() <= MAX_ERROR_LENGTH ? message : message.substring(0, MAX_ERROR_LENGTH);
	}

	public record DeletionPlan(String taskId, String cleanupJobId, String initialStatus) {
	}
}
