package com.example.videoplatform.workflow;

import com.example.videoplatform.transcript.TranscriptResult;
import java.time.Instant;
import java.util.List;

public final class WorkflowDtos {

	private WorkflowDtos() {
	}

	public record TaskView(
			String taskId,
			String videoId,
			String tenantId,
			String owner,
			String fileName,
			String transcript,
			List<TranscriptResult.Segment> transcriptSegments,
			String transcriptLanguage,
			Long transcriptDurationMs,
			int transcriptVersion,
			boolean mediaRetained,
			boolean transcriptRetained,
			String summary,
			VideoTask.TaskStatus status,
			String errorMessage,
			Instant createdAt,
			Instant updatedAt) {

		public static TaskView from(VideoTask task) {
			return new TaskView(
					task.getTaskId(),
					task.getVideoId(),
					task.getTenantId(),
					task.getOwner(),
					task.getFileName(),
					task.getTranscript(),
					task.getTranscriptResult().segments(),
					task.getTranscriptResult().language(),
					task.getTranscriptResult().durationMs(),
					task.getTranscriptVersion(),
					task.getStoragePath() != null && !task.getStoragePath().isBlank(),
					task.getTranscript() != null,
					task.getSummary(),
					task.getStatus(),
					task.getErrorMessage(),
					task.getCreatedAt(),
					task.getUpdatedAt());
		}
	}

	public record TaskQuotaView(long activeTasks, int maxActiveTasksPerUser, long remainingSlots, boolean limited) {
	}

	public record RuntimeView(String dispatchMode, boolean mqEnabled, String transcriptMode,
			String summaryMode, long mockDelayMs, int maxActiveTasksPerUser,
			int mqConsumerThreads, String storageType, String jwtAlgorithm,
			boolean oidcEnabled, boolean modelEgressAllowed, boolean retentionEnabled,
			int mediaRetentionDays, int transcriptRetentionDays, int auditRetentionDays) {
	}

	public record TaskDeletionView(String taskId, String mediaCleanupStatus) {
	}
}
