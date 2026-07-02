package com.example.videoplatform.workflow;

import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

import java.util.List;
import java.util.UUID;

@Service
public class VideoTaskService {

	private final VideoTaskRepository taskRepository;

	public VideoTaskService(VideoTaskRepository taskRepository) {
		this.taskRepository = taskRepository;
	}

	@Transactional
	public VideoTask createTask(String owner, String fileName, String storagePath) {
		return createTask(owner, fileName, storagePath, null);
	}

	@Transactional
	public VideoTask createTask(String owner, String fileName, String storagePath, String contentMd5) {
		String taskId = UUID.randomUUID().toString();
		String videoId = UUID.randomUUID().toString();
		VideoTask task = new VideoTask(taskId, videoId, owner, fileName, storagePath, contentMd5);
		return taskRepository.save(task);
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
	public void deleteTask(String taskId, String owner) {
		VideoTask task = requireTask(taskId, owner);
		taskRepository.delete(task);
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
	public void completeTranscript(String taskId, String transcript) {
		VideoTask task = requireManagedTask(taskId);
		task.setTranscript(transcript);
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

	/**
	 * 幂等占位：仅当任务仍处于 QUEUED 时抢占为 TRANSCRIBING，返回是否抢占成功。
	 *
	 * <p>MQ 至少一次投递会导致同一 taskId 被重复消费；只有把状态从 QUEUED 原子推进的那个
	 * worker 返回 true 并继续处理，其余重复投递返回 false 直接跳过，避免重复执行昂贵处理。
	 */
	@Transactional
	public boolean claimForProcessing(String taskId) {
		VideoTask task = requireManagedTask(taskId);
		if (task.getStatus() != VideoTask.TaskStatus.QUEUED) {
			return false;
		}
		task.setStatus(VideoTask.TaskStatus.TRANSCRIBING);
		return true;
	}

	/** 从已就绪的资产直接复用结果，秒完成任务（内容级去重命中路径）。 */
	@Transactional
	public void completeFromAsset(String taskId, String transcript, String summary) {
		VideoTask task = requireManagedTask(taskId);
		task.setTranscript(transcript);
		task.setSummary(summary);
		task.setStatus(VideoTask.TaskStatus.COMPLETED);
	}

	/**
	 * fan-out：把结果写入同一内容（同 MD5）的所有未完成任务并标记 COMPLETED。
	 * 单飞的赢家处理完后调用，一并完成那些因抢锁失败而等待的同内容任务。
	 */
	@Transactional
	public int completeAllByContentMd5(String contentMd5, String transcript, String summary) {
		int affected = 0;
		for (VideoTask task : taskRepository.findByContentMd5(contentMd5)) {
			if (task.getStatus() != VideoTask.TaskStatus.COMPLETED) {
				task.setTranscript(transcript);
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
}
