package com.example.videoplatform.workflow;

import com.example.videoplatform.auth.UserAccountRepository;
import com.example.videoplatform.config.AppProperties;
import com.example.videoplatform.transcript.TranscriptResult;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

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

	public VideoTaskService(VideoTaskRepository taskRepository, UserAccountRepository userAccountRepository,
			AppProperties appProperties) {
		this.taskRepository = taskRepository;
		this.userAccountRepository = userAccountRepository;
		this.appProperties = appProperties;
	}

	@Transactional
	public VideoTask createTask(String owner, String fileName, String storagePath) {
		return createTask(owner, fileName, storagePath, null);
	}

	@Transactional
	public VideoTask createTask(String owner, String fileName, String storagePath, String contentMd5) {
		assertCanCreateTask(owner);
		String taskId = UUID.randomUUID().toString();
		String videoId = UUID.randomUUID().toString();
		VideoTask task = new VideoTask(taskId, videoId, owner, fileName, storagePath, contentMd5);
		return taskRepository.save(task);
	}

	/**
	 * 在写入文件前给用户一个快速反馈；createTask 内部还会再次检查，覆盖并发竞争窗口。
	 */
	@Transactional
	public void assertCanCreateTask(String owner) {
		int limit = appProperties.getQuota().getMaxActiveTasksPerUser();
		if (limit <= 0) {
			return;
		}
		lockOwner(owner);
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

	/** 短事务：写入摘要结果并标记 COMPLETED。 */
	@Transactional
	public void completeSummary(String taskId, String summary) {
		VideoTask task = requireManagedTask(taskId);
		task.setSummary(summary);
		task.setStatus(VideoTask.TaskStatus.COMPLETED);
	}

	/** 短事务：标记任务失败并保存（已截断的）错误信息。 */
	@Transactional
	public void markFailed(String taskId, String errorMessage) {
		VideoTask task = requireManagedTask(taskId);
		task.setStatus(VideoTask.TaskStatus.FAILED);
		task.setErrorMessage(errorMessage);
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

	private void lockOwner(String owner) {
		userAccountRepository.findByUserId(owner)
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
		return taskRepository.updateStatusIfCurrent(
				taskId, VideoTask.TaskStatus.QUEUED, VideoTask.TaskStatus.TRANSCRIBING, Instant.now()) > 0;
	}

	/** 从已就绪的资产直接复用结果，秒完成任务（内容级去重命中路径）。 */
	@Transactional
	public void completeFromAsset(String taskId, TranscriptResult transcript, String summary) {
		VideoTask task = requireManagedTask(taskId);
		task.setTranscriptResult(transcript);
		task.setSummary(summary);
		task.setStatus(VideoTask.TaskStatus.COMPLETED);
	}

	/**
	 * fan-out：把结果写入同一内容（同 MD5）的所有未完成任务并标记 COMPLETED。
	 * 单飞的赢家处理完后调用，一并完成那些因抢锁失败而等待的同内容任务。
	 */
	@Transactional
	public int completeAllByContentMd5(String contentMd5, TranscriptResult transcript, String summary) {
		int affected = 0;
		for (VideoTask task : taskRepository.findByContentMd5(contentMd5)) {
			if (task.getStatus() != VideoTask.TaskStatus.COMPLETED) {
				task.setTranscriptResult(transcript);
				task.setSummary(summary);
				task.setStatus(VideoTask.TaskStatus.COMPLETED);
				affected++;
			}
		}
		return affected;
	}

	/** fan-out 失败版：同内容的所有未完成任务一并标记 FAILED。 */
	@Transactional
	public int failAllByContentMd5(String contentMd5, String errorMessage) {
		int affected = 0;
		for (VideoTask task : taskRepository.findByContentMd5(contentMd5)) {
			if (task.getStatus() != VideoTask.TaskStatus.COMPLETED
					&& task.getStatus() != VideoTask.TaskStatus.FAILED) {
				task.setStatus(VideoTask.TaskStatus.FAILED);
				task.setErrorMessage(errorMessage);
				affected++;
			}
		}
		return affected;
	}

	/**
	 * 定时补偿：把长时间未推进的任务重置为 QUEUED 并返回 taskId，调用方随后重新发布。
	 *
	 * <p>纳入 QUEUED 是为了覆盖 MQ 投递失败、死信前后或本地线程池拒绝后留下的老任务；
	 * 纳入 TRANSCRIBING/SUMMARIZING 是为了覆盖进程崩溃、单飞赢家中断等导致的悬挂任务。
	 * 重复发布可由 {@link #claimForProcessing(String)} 的状态抢占保证幂等。
	 */
	@Transactional
	public List<String> requeueStaleTasks(Instant cutoff) {
		List<VideoTask.TaskStatus> retryableStatuses = List.of(
				VideoTask.TaskStatus.QUEUED,
				VideoTask.TaskStatus.TRANSCRIBING,
				VideoTask.TaskStatus.SUMMARIZING);
		List<String> taskIds = new ArrayList<>();
		for (VideoTask task : taskRepository.findByStatusInAndUpdatedAtBefore(retryableStatuses, cutoff)) {
			task.setStatus(VideoTask.TaskStatus.QUEUED);
			taskIds.add(task.getTaskId());
		}
		return taskIds;
	}
}
