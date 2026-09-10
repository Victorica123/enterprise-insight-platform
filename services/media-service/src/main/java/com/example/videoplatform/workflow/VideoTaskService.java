package com.example.videoplatform.workflow;

import com.example.videoplatform.auth.UserAccount;
import com.example.videoplatform.auth.UserAccountRepository;
import com.example.videoplatform.config.AppProperties;
import com.example.videoplatform.integration.TranscriptEventOutboxService;
import com.example.videoplatform.transcript.TranscriptResult;
import org.slf4j.MDC;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

import java.time.Duration;
import java.time.Instant;
import java.util.ArrayList;
import java.util.List;
import java.util.Optional;
import java.util.UUID;

@Service
public class VideoTaskService {

	private final VideoTaskRepository taskRepository;
	private final UserAccountRepository userAccountRepository;
	private final AppProperties appProperties;
	private final TranscriptEventOutboxService transcriptOutboxService;
	private final WorkflowDispatchOutboxService workflowDispatchOutboxService;

	public VideoTaskService(VideoTaskRepository taskRepository, UserAccountRepository userAccountRepository,
			AppProperties appProperties, TranscriptEventOutboxService transcriptOutboxService,
			WorkflowDispatchOutboxService workflowDispatchOutboxService) {
		this.taskRepository = taskRepository;
		this.userAccountRepository = userAccountRepository;
		this.appProperties = appProperties;
		this.transcriptOutboxService = transcriptOutboxService;
		this.workflowDispatchOutboxService = workflowDispatchOutboxService;
	}

	@Transactional
	public VideoTask createTask(String owner, String fileName, String storagePath) {
		return createTask(owner, fileName, storagePath, null);
	}

	@Transactional
	public VideoTask createTask(String owner, String fileName, String storagePath, String contentMd5) {
		UserAccount account = lockOwner(owner);
		assertWithinQuota(owner);
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
		lockOwner(owner);
		assertWithinQuota(owner);
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

	/**
	 * 在写入文件前给用户一个快速反馈；createTask 内部还会再次检查，覆盖并发竞争窗口。
	 */
	@Transactional
	public void assertCanCreateTask(String owner) {
		lockOwner(owner);
		assertWithinQuota(owner);
	}

	private void assertWithinQuota(String owner) {
		int limit = appProperties.getQuota().getMaxActiveTasksPerUser();
		if (limit <= 0) {
			return;
		}
		long activeCount = countActiveTasks(owner);
		if (activeCount >= limit) {
			throw new ActiveTaskLimitExceededException(limit, activeCount);
		}
	}

	@Transactional(readOnly = true)
	public WorkflowDtos.TaskQuotaView getTaskQuota(String owner) {
		int limit = appProperties.getQuota().getMaxActiveTasksPerUser();
		long activeCount = countActiveTasks(owner);
		long remaining = limit > 0 ? Math.max(0, limit - activeCount) : -1;
		return new WorkflowDtos.TaskQuotaView(activeCount, limit, remaining, limit > 0);
	}

	@Transactional(readOnly = true)
	public Optional<VideoTask> findLatestTaskByStoragePath(String owner, String storagePath) {
		return taskRepository.findFirstByOwnerAndStoragePathOrderByCreatedAtDesc(owner, storagePath);
	}

	/**
	 * 内部使用：后台工作流处理器调用，不校验owner
	 */
	@Transactional(readOnly = true)
	public VideoTask requireTask(String taskId) {
		return taskRepository.findById(taskId)
				.orElseThrow(() -> new IllegalArgumentException("任务不存在: " + taskId));
	}

	/**
	 * 带owner校验：Controller调用，确保用户只能查自己的任务
	 */
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

	/**
	 * 短事务：仅推进状态。工作流各阶段之间独立提交，使前端轮询能看到中间进度，
	 * 且避免在外部 I/O（FFmpeg / Whisper / LLM）期间长时间占用数据库连接。
	 */
	@Transactional
	public void updateStatus(String taskId, VideoTask.TaskStatus status) {
		VideoTask task = requireManagedTask(taskId);
		task.setStatus(status);
	}

	/** 短事务：写入转写结果并进入 SUMMARIZING 状态。 */
	@Transactional
	public void completeTranscript(String taskId, TranscriptResult transcript) {
		VideoTask task = requireManagedTask(taskId);
		task.setTranscriptResult(transcript);
		task.setStatus(VideoTask.TaskStatus.SUMMARIZING);
	}

	/**
	 * Lease-fenced transcript completion. The conditional update is important:
	 * checking ownership in Java alone still leaves a race with the reaper.
	 */
	@Transactional
	public boolean completeTranscript(String taskId, TranscriptResult transcript, String leaseId) {
		return taskRepository.completeTranscriptWithLease(
				taskId, VideoTask.TaskStatus.TRANSCRIBING, VideoTask.TaskStatus.SUMMARIZING,
				leaseId, transcript.text(), transcript.segmentsJson(), transcript.language(),
				transcript.durationMs(), Instant.now()) > 0;
	}

	/** 短事务：写入摘要结果并标记 COMPLETED。 */
	@Transactional
	public void completeSummary(String taskId, String summary) {
		VideoTask task = requireManagedTask(taskId);
		task.setSummary(summary);
		task.setStatus(VideoTask.TaskStatus.COMPLETED);
		task.clearProcessingLease();
		transcriptOutboxService.enqueue(task);
	}

	/** Lease-fenced summary completion, including the atomic outbox write. */
	@Transactional
	public boolean completeSummary(String taskId, String summary, String leaseId) {
		int updated = taskRepository.completeSummaryWithLease(
				taskId, VideoTask.TaskStatus.SUMMARIZING, VideoTask.TaskStatus.COMPLETED,
				leaseId, summary, Instant.now());
		if (updated == 0) {
			return false;
		}
		transcriptOutboxService.enqueue(requireManagedTask(taskId));
		return true;
	}

	/** 短事务：标记任务失败并保存（已截断的）错误信息。 */
	@Transactional
	public void markFailed(String taskId, String errorMessage) {
		VideoTask task = requireManagedTask(taskId);
		task.setStatus(VideoTask.TaskStatus.FAILED);
		task.setErrorMessage(errorMessage);
		task.clearProcessingLease();
	}

	/** Lease-fenced failure transition used when an external stage fails. */
	@Transactional
	public boolean markFailed(String taskId, String errorMessage, String leaseId) {
		return taskRepository.markFailedWithLease(
				taskId,
				List.of(VideoTask.TaskStatus.TRANSCRIBING, VideoTask.TaskStatus.SUMMARIZING),
				VideoTask.TaskStatus.FAILED, leaseId, errorMessage, Instant.now()) > 0;
	}

	private VideoTask requireManagedTask(String taskId) {
		return taskRepository.findById(taskId)
				.orElseThrow(() -> new IllegalArgumentException("任务不存在: " + taskId));
	}

	private long countActiveTasks(String owner) {
		return taskRepository.countByOwnerAndStatusIn(owner, List.of(
				VideoTask.TaskStatus.QUEUED,
				VideoTask.TaskStatus.TRANSCRIBING,
				VideoTask.TaskStatus.SUMMARIZING));
	}

	private UserAccount lockOwner(String owner) {
		return userAccountRepository.findByUserId(owner)
				.orElseThrow(() -> new IllegalArgumentException("用户不存在: " + owner));
	}

	/**
	 * 幂等占位：仅当任务仍处于 QUEUED 时原子推进为 TRANSCRIBING，返回是否抢占成功。
	 *
	 * <p>MQ 至少一次投递会导致同一 taskId 被重复消费；用条件 UPDATE（影响行数=1 才算抢占成功）
	 * 保证并发消费者中只有一个继续处理，其余重复投递直接跳过，避免重复执行昂贵处理。
	 */
	@Transactional
	public boolean claimForProcessing(String taskId) {
		return claimForProcessingWithLease(taskId).isPresent();
	}

	/** Claim a task and return the fencing token used by heartbeat renewal. */
	@Transactional
	public Optional<String> claimForProcessingWithLease(String taskId) {
		Instant now = Instant.now();
		String leaseId = UUID.randomUUID().toString();
		Duration leaseDuration = appProperties.getWorkflow().getTaskLeaseDuration();
		if (leaseDuration == null || leaseDuration.isZero() || leaseDuration.isNegative()) {
			leaseDuration = Duration.ofMinutes(15);
		}
		int updated = taskRepository.claimWithLease(
				taskId, VideoTask.TaskStatus.QUEUED, VideoTask.TaskStatus.TRANSCRIBING,
				leaseId, now.plus(leaseDuration), now);
		return updated > 0 ? Optional.of(leaseId) : Optional.empty();
	}

	/** Renew only the lease that this worker owns; a lost lease becomes a fencing signal. */
	@Transactional
	public boolean renewProcessingLease(String taskId, String leaseId) {
		Instant now = Instant.now();
		Duration leaseDuration = appProperties.getWorkflow().getTaskLeaseDuration();
		if (leaseDuration == null || leaseDuration.isZero() || leaseDuration.isNegative()) {
			leaseDuration = Duration.ofMinutes(15);
		}
		return taskRepository.renewLease(
				taskId, leaseId,
				List.of(VideoTask.TaskStatus.TRANSCRIBING, VideoTask.TaskStatus.SUMMARIZING),
				now.plus(leaseDuration), now) > 0;
	}

	public long leaseHeartbeatIntervalMillis() {
		Duration leaseDuration = appProperties.getWorkflow().getTaskLeaseDuration();
		if (leaseDuration == null || leaseDuration.isZero() || leaseDuration.isNegative()) {
			leaseDuration = Duration.ofMinutes(15);
		}
		return Math.max(1000L, leaseDuration.toMillis() / 3);
	}

	/** 从已就绪的资产直接复用结果，秒完成任务（内容级去重命中路径）。 */
	@Transactional
	public void completeFromAsset(String taskId, TranscriptResult transcript, String summary) {
		VideoTask task = requireManagedTask(taskId);
		task.setTranscriptResult(transcript);
		task.setSummary(summary);
		task.setStatus(VideoTask.TaskStatus.COMPLETED);
		task.clearProcessingLease();
		transcriptOutboxService.enqueue(task);
	}

	/**
	 * fan-out：把结果写入同一内容（同 MD5）的所有未完成任务并标记 COMPLETED。
	 * 单飞的赢家处理完后调用，一并完成那些因抢锁失败而等待的同内容任务。
	 */
	@Transactional
	public int completeAllByContentMd5(String contentMd5, TranscriptResult transcript, String summary) {
		return completeAllByContentMd5("legacy", contentMd5, transcript, summary);
	}

	@Transactional
	public int completeAllByContentMd5(String tenantId, String contentMd5, TranscriptResult transcript, String summary) {
		int affected = 0;
		for (VideoTask task : taskRepository.findByTenantIdAndContentMd5(tenantId, contentMd5)) {
			if (task.getStatus() != VideoTask.TaskStatus.COMPLETED) {
				task.setTranscriptResult(transcript);
				task.setSummary(summary);
				task.setStatus(VideoTask.TaskStatus.COMPLETED);
				task.clearProcessingLease();
				transcriptOutboxService.enqueue(task);
				affected++;
			}
		}
		return affected;
	}

	/**
	 * Lease-fenced fan-out. The coordinator is completed with a conditional
	 * update before other duplicate tasks are copied, so a reaper takeover
	 * cannot let an old worker complete its own task.
	 */
	@Transactional
	public boolean completeAllByContentMd5(
			String tenantId, String contentMd5, TranscriptResult transcript, String summary,
			String coordinatorTaskId, String leaseId) {
		List<VideoTask.TaskStatus> activeStatuses = List.of(
				VideoTask.TaskStatus.QUEUED,
				VideoTask.TaskStatus.TRANSCRIBING,
				VideoTask.TaskStatus.SUMMARIZING);
		int coordinatorUpdated = taskRepository.completeContentWithLease(
				coordinatorTaskId, activeStatuses, VideoTask.TaskStatus.COMPLETED, leaseId,
				transcript.text(), transcript.segmentsJson(), transcript.language(), transcript.durationMs(),
				summary, Instant.now());
		if (coordinatorUpdated == 0) {
			return false;
		}
		transcriptOutboxService.enqueue(requireManagedTask(coordinatorTaskId));
		for (VideoTask task : taskRepository.findByTenantIdAndContentMd5(tenantId, contentMd5)) {
			if (!task.getTaskId().equals(coordinatorTaskId)
					&& activeStatuses.contains(task.getStatus())) {
				task.setTranscriptResult(transcript);
				task.setSummary(summary);
				task.setStatus(VideoTask.TaskStatus.COMPLETED);
				task.clearProcessingLease();
				transcriptOutboxService.enqueue(task);
			}
		}
		return true;
	}

	/** fan-out 失败版：同内容的所有未完成任务一并标记 FAILED。 */
	@Transactional
	public int failAllByContentMd5(String contentMd5, String errorMessage) {
		return failAllByContentMd5("legacy", contentMd5, errorMessage);
	}

	@Transactional
	public int failAllByContentMd5(String tenantId, String contentMd5, String errorMessage) {
		int affected = 0;
		for (VideoTask task : taskRepository.findByTenantIdAndContentMd5(tenantId, contentMd5)) {
			if (task.getStatus() != VideoTask.TaskStatus.COMPLETED
					&& task.getStatus() != VideoTask.TaskStatus.FAILED) {
				task.setStatus(VideoTask.TaskStatus.FAILED);
				task.setErrorMessage(errorMessage);
				task.clearProcessingLease();
				affected++;
			}
		}
		return affected;
	}

	/** Complete the coordinator failure conditionally, then fail duplicate tasks. */
	@Transactional
	public boolean failAllByContentMd5(
			String tenantId, String contentMd5, String errorMessage,
			String coordinatorTaskId, String leaseId) {
		List<VideoTask.TaskStatus> activeStatuses = List.of(
				VideoTask.TaskStatus.QUEUED,
				VideoTask.TaskStatus.TRANSCRIBING,
				VideoTask.TaskStatus.SUMMARIZING);
		if (taskRepository.markFailedWithLease(
				coordinatorTaskId, activeStatuses, VideoTask.TaskStatus.FAILED,
				leaseId, errorMessage, Instant.now()) == 0) {
			return false;
		}
		for (VideoTask task : taskRepository.findByTenantIdAndContentMd5(tenantId, contentMd5)) {
			if (!task.getTaskId().equals(coordinatorTaskId)
					&& activeStatuses.contains(task.getStatus())) {
				task.setStatus(VideoTask.TaskStatus.FAILED);
				task.setErrorMessage(errorMessage);
				task.clearProcessingLease();
			}
		}
		return true;
	}

	/**
	 * 定时补偿：把长时间未推进的任务重置为 QUEUED，并在同一事务重建调度意图。
	 *
	 * <p>纳入 QUEUED 是为了覆盖 MQ 投递失败、死信前后或本地线程池拒绝后留下的老任务；
	 * 纳入 TRANSCRIBING/SUMMARIZING 是为了覆盖进程崩溃、单飞赢家中断等导致的悬挂任务。
	 * 重复投递可由 {@link #claimForProcessing(String)} 的状态抢占保证幂等；返回 taskId 仅供日志与指标。
	 */
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
				workflowDispatchOutboxService.enqueue(taskId);
				taskIds.add(taskId);
			}
		}
		return taskIds;
	}
}
