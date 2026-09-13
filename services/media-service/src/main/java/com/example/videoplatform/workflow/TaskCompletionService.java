package com.example.videoplatform.workflow;

import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;
import java.time.Instant;
import java.util.List;
import com.example.videoplatform.integration.TranscriptEventOutboxService;
import com.example.videoplatform.transcript.TranscriptResult;

@Service
public class TaskCompletionService {
	private final VideoTaskRepository taskRepository;
	private final TranscriptEventOutboxService transcriptOutboxService;

	public TaskCompletionService(VideoTaskRepository taskRepository, TranscriptEventOutboxService transcriptOutboxService) {
		this.taskRepository = taskRepository;
		this.transcriptOutboxService = transcriptOutboxService;
	}

	@Transactional
	public void updateStatus(String taskId, VideoTask.TaskStatus status) {
		VideoTask task = requireManagedTask(taskId);
		task.setStatus(status);
	}

	@Transactional
	public void completeTranscript(String taskId, TranscriptResult transcript) {
		VideoTask task = requireManagedTask(taskId);
		task.setTranscriptResult(transcript);
		task.setStatus(VideoTask.TaskStatus.SUMMARIZING);
	}

	@Transactional
	public boolean completeTranscript(String taskId, TranscriptResult transcript, String leaseId) {
		return taskRepository.completeTranscriptWithLease(
				taskId, VideoTask.TaskStatus.TRANSCRIBING, VideoTask.TaskStatus.SUMMARIZING,
				leaseId, transcript.text(), transcript.segmentsJson(), transcript.language(),
				transcript.durationMs(), Instant.now()) > 0;
	}

	@Transactional
	public void completeSummary(String taskId, String summary) {
		VideoTask task = requireManagedTask(taskId);
		task.setSummary(summary);
		task.setStatus(VideoTask.TaskStatus.COMPLETED);
		task.clearProcessingLease();
		transcriptOutboxService.enqueue(task);
	}

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

	@Transactional
	public void markFailed(String taskId, String errorMessage) {
		VideoTask task = requireManagedTask(taskId);
		task.setStatus(VideoTask.TaskStatus.FAILED);
		task.setErrorMessage(errorMessage);
		task.clearProcessingLease();
	}

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

	@Transactional
	public void completeFromAsset(String taskId, TranscriptResult transcript, String summary) {
		VideoTask task = requireManagedTask(taskId);
		task.setTranscriptResult(transcript);
		task.setSummary(summary);
		task.setStatus(VideoTask.TaskStatus.COMPLETED);
		task.clearProcessingLease();
		transcriptOutboxService.enqueue(task);
	}

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
}
