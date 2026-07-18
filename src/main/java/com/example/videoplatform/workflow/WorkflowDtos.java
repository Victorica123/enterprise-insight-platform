package com.example.videoplatform.workflow;

import java.time.Instant;

public final class WorkflowDtos {

	private WorkflowDtos() {
	}

	public record TaskView(
			String taskId,
			String videoId,
			String owner,
			String fileName,
			String transcript,
			String summary,
			VideoTask.TaskStatus status,
			String errorMessage,
			Instant createdAt,
			Instant updatedAt) {

		public static TaskView from(VideoTask task) {
			return new TaskView(
					task.getTaskId(),
					task.getVideoId(),
					task.getOwner(),
					task.getFileName(),
					task.getTranscript(),
					task.getSummary(),
					task.getStatus(),
					task.getErrorMessage(),
					task.getCreatedAt(),
					task.getUpdatedAt());
		}
	}

	public record TaskQuotaView(long activeTasks, int maxActiveTasksPerUser, long remainingSlots, boolean limited) {
	}

	public record RuntimeView(String dispatchMode, boolean mqEnabled, long mockDelayMs,
			int maxActiveTasksPerUser, int mqConsumerThreads, String storageType) {
	}
}
