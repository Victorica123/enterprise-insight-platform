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
		String taskId = UUID.randomUUID().toString();
		String videoId = UUID.randomUUID().toString();
		VideoTask task = new VideoTask(taskId, videoId, owner, fileName, storagePath);
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
}
