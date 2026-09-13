package com.example.videoplatform.workflow;

import com.example.videoplatform.auth.UserAccount;
import com.example.videoplatform.transcript.TranscriptResult;
import org.slf4j.MDC;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;
import java.time.Instant;
import java.util.List;
import java.util.Optional;
import java.util.UUID;

/** Task access and intake facade. Domain transactions live in the quota, lease and completion services. */
@Service
public class VideoTaskService {
	private final VideoTaskRepository taskRepository;
	private final TaskQuotaService taskQuotaService;
	private final TaskLeaseService taskLeaseService;
	private final TaskCompletionService taskCompletionService;
	private final WorkflowDispatchOutboxService workflowDispatchOutboxService;

	public VideoTaskService(VideoTaskRepository taskRepository, TaskQuotaService taskQuotaService, TaskLeaseService taskLeaseService, TaskCompletionService taskCompletionService, WorkflowDispatchOutboxService workflowDispatchOutboxService) {
		this.taskRepository = taskRepository;
		this.taskQuotaService = taskQuotaService;
		this.taskLeaseService = taskLeaseService;
		this.taskCompletionService = taskCompletionService;
		this.workflowDispatchOutboxService = workflowDispatchOutboxService;
	}

	@Transactional
	public VideoTask createTask(String owner, String fileName, String storagePath) {
		return createTask(owner, fileName, storagePath, null);
	}

	@Transactional
	public VideoTask createTask(String owner, String fileName, String storagePath, String contentMd5) {
		UserAccount account = taskQuotaService.lockOwner(owner);
		taskQuotaService.assertWithinQuota(owner);
		String tenantId = account.getPrimaryTenantId() == null ? "legacy" : account.getPrimaryTenantId();
		return persistNewTask(owner, tenantId, fileName, storagePath, contentMd5);
	}

	@Transactional
	public VideoTask createTaskInWorkspace(
			String owner, String tenantId, String fileName, String storagePath) {
		return createTaskInWorkspace(owner, tenantId, fileName, storagePath, null);
	}

	@Transactional
	public VideoTask createTaskInWorkspace(
			String owner, String tenantId, String fileName, String storagePath, String contentMd5) {
		taskQuotaService.lockOwner(owner);
		taskQuotaService.assertWithinQuota(owner);
		return persistNewTask(owner, tenantId, fileName, storagePath, contentMd5);
	}

	private VideoTask persistNewTask(
			String owner, String tenantId, String fileName, String storagePath, String contentMd5) {
		String taskId = UUID.randomUUID().toString();
		String videoId = UUID.randomUUID().toString();
		String traceId = MDC.get("traceId") == null ? taskId : MDC.get("traceId");
		VideoTask task = new VideoTask(
				taskId, videoId, tenantId, owner, fileName, storagePath, contentMd5, traceId);
		taskRepository.save(task);
		workflowDispatchOutboxService.enqueue(taskId);
		return task;
	}

	@Transactional
	public void assertCanCreateTask(String owner) {
		taskQuotaService.assertCanCreateTask(owner);
	}

	@Transactional(readOnly = true)
	public WorkflowDtos.TaskQuotaView getTaskQuota(String owner) {
		return taskQuotaService.getTaskQuota(owner);
	}

	@Transactional(readOnly = true)
	public Optional<VideoTask> findLatestTaskByStoragePath(String owner, String storagePath) {
		return taskRepository.findFirstByOwnerAndStoragePathOrderByCreatedAtDesc(owner, storagePath);
	}

	@Transactional(readOnly = true)
	public VideoTask requireTask(String taskId) {
		return taskRepository.findById(taskId)
				.orElseThrow(() -> new IllegalArgumentException("任务不存在: " + taskId));
	}

	@Transactional(readOnly = true)
	public VideoTask requireTask(String taskId, String owner) {
		return taskRepository.findByTaskIdAndOwner(taskId, owner)
				.orElseThrow(() -> new IllegalArgumentException("任务不存在或无权限: " + taskId));
	}

	@Transactional(readOnly = true)
	public List<VideoTask> listTasksByOwner(String owner) {
		return taskRepository.findByOwnerOrderByCreatedAtDesc(owner);
	}

	@Transactional(readOnly = true)
	public List<VideoTask> listTasksForWorkspace(
			String tenantId, String userId, boolean teamWorkspace) {
		return teamWorkspace
				? taskRepository.findByTenantIdOrderByCreatedAtDesc(tenantId)
				: taskRepository.findByTenantIdAndOwnerOrderByCreatedAtDesc(tenantId, userId);
	}

	@Transactional(readOnly = true)
	public VideoTask requireTaskForWorkspace(
			String taskId, String tenantId, String userId, boolean teamWorkspace) {
		return (teamWorkspace
				? taskRepository.findByTaskIdAndTenantId(taskId, tenantId)
				: taskRepository.findByTaskIdAndTenantIdAndOwner(taskId, tenantId, userId))
				.orElseThrow(() -> new IllegalArgumentException("任务不存在或无权限: " + taskId));
	}

	@Transactional
	public VideoTask retryFailedTaskForWorkspace(
			String taskId, String tenantId, String userId, boolean teamWorkspace) {
		VideoTask task = requireTaskForWorkspace(taskId, tenantId, userId, teamWorkspace);
		if (task.getStatus() != VideoTask.TaskStatus.FAILED) {
			throw new IllegalArgumentException("只有失败任务可以重试: " + taskId);
		}
		assertCanCreateTask(userId);
		task.setErrorMessage(null);
		task.setStatus(VideoTask.TaskStatus.QUEUED);
		workflowDispatchOutboxService.enqueue(taskId);
		return task;
	}

	@Transactional
	public VideoTask retryFailedTask(String taskId, String owner) {
		VideoTask task = taskRepository.findByTaskIdAndOwner(taskId, owner)
				.orElseThrow(() -> new IllegalArgumentException("任务不存在或无权限: " + taskId));
		if (task.getStatus() != VideoTask.TaskStatus.FAILED) {
			throw new IllegalArgumentException("只有失败任务可以重试: " + taskId);
		}
		assertCanCreateTask(owner);
		task.setErrorMessage(null);
		task.setStatus(VideoTask.TaskStatus.QUEUED);
		workflowDispatchOutboxService.enqueue(taskId);
		return task;
	}

	@Transactional
	public VideoTask save(VideoTask task) {
		return taskRepository.save(task);
	}

	@Transactional
	public void updateStatus(String taskId, VideoTask.TaskStatus status) {
		taskCompletionService.updateStatus(taskId, status);
	}

	@Transactional
	public void completeTranscript(String taskId, TranscriptResult transcript) {
		taskCompletionService.completeTranscript(taskId, transcript);
	}

	@Transactional
	public boolean completeTranscript(String taskId, TranscriptResult transcript, String leaseId) {
		return taskCompletionService.completeTranscript(taskId, transcript, leaseId);
	}

	@Transactional
	public void completeSummary(String taskId, String summary) {
		taskCompletionService.completeSummary(taskId, summary);
	}

	@Transactional
	public boolean completeSummary(String taskId, String summary, String leaseId) {
		return taskCompletionService.completeSummary(taskId, summary, leaseId);
	}

	@Transactional
	public void markFailed(String taskId, String errorMessage) {
		taskCompletionService.markFailed(taskId, errorMessage);
	}

	@Transactional
	public boolean markFailed(String taskId, String errorMessage, String leaseId) {
		return taskCompletionService.markFailed(taskId, errorMessage, leaseId);
	}

	@Transactional
	public boolean claimForProcessing(String taskId) {
		return taskLeaseService.claimForProcessing(taskId);
	}

	@Transactional
	public Optional<String> claimForProcessingWithLease(String taskId) {
		return taskLeaseService.claimForProcessingWithLease(taskId);
	}

	@Transactional
	public boolean renewProcessingLease(String taskId, String leaseId) {
		return taskLeaseService.renewProcessingLease(taskId, leaseId);
	}

	public long leaseHeartbeatIntervalMillis() {
		return taskLeaseService.leaseHeartbeatIntervalMillis();
	}

	@Transactional
	public void completeFromAsset(String taskId, TranscriptResult transcript, String summary) {
		taskCompletionService.completeFromAsset(taskId, transcript, summary);
	}

	@Transactional
	public int completeAllByContentMd5(String contentMd5, TranscriptResult transcript, String summary) {
		return taskCompletionService.completeAllByContentMd5(contentMd5, transcript, summary);
	}

	@Transactional
	public int completeAllByContentMd5(String tenantId, String contentMd5, TranscriptResult transcript, String summary) {
		return taskCompletionService.completeAllByContentMd5(tenantId, contentMd5, transcript, summary);
	}

	@Transactional
	public boolean completeAllByContentMd5(
			String tenantId, String contentMd5, TranscriptResult transcript, String summary,
			String coordinatorTaskId, String leaseId) {
		return taskCompletionService.completeAllByContentMd5(tenantId, contentMd5, transcript, summary, coordinatorTaskId, leaseId);
	}

	@Transactional
	public int failAllByContentMd5(String contentMd5, String errorMessage) {
		return taskCompletionService.failAllByContentMd5(contentMd5, errorMessage);
	}

	@Transactional
	public int failAllByContentMd5(String tenantId, String contentMd5, String errorMessage) {
		return taskCompletionService.failAllByContentMd5(tenantId, contentMd5, errorMessage);
	}

	@Transactional
	public boolean failAllByContentMd5(
			String tenantId, String contentMd5, String errorMessage,
			String coordinatorTaskId, String leaseId) {
		return taskCompletionService.failAllByContentMd5(tenantId, contentMd5, errorMessage, coordinatorTaskId, leaseId);
	}

	@Transactional
	public List<String> requeueStaleTasks(Instant cutoff) {
		return taskLeaseService.requeueStaleTasks(cutoff);
	}
}
