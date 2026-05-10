package com.example.videoplatform.workflow;

import java.time.Instant;

public class VideoTask {

	private final String taskId;
	private final String videoId;
	private final String owner;
	private final String fileName;
	private final String storagePath;
	private volatile String transcript;
	private volatile String summary;
	private volatile TaskStatus status;
	private volatile String errorMessage;
	private final Instant createdAt;
	private volatile Instant updatedAt;

	public VideoTask(String taskId, String videoId, String owner, String fileName, String storagePath) {
		this.taskId = taskId;
		this.videoId = videoId;
		this.owner = owner;
		this.fileName = fileName;
		this.storagePath = storagePath;
		this.status = TaskStatus.QUEUED;
		this.createdAt = Instant.now();
		this.updatedAt = this.createdAt;
	}

	public String getTaskId() {
		return taskId;
	}

	public String getVideoId() {
		return videoId;
	}

	public String getOwner() {
		return owner;
	}

	public String getFileName() {
		return fileName;
	}

	public String getStoragePath() {
		return storagePath;
	}

	public String getTranscript() {
		return transcript;
	}

	public void setTranscript(String transcript) {
		this.transcript = transcript;
		this.updatedAt = Instant.now();
	}

	public String getSummary() {
		return summary;
	}

	public void setSummary(String summary) {
		this.summary = summary;
		this.updatedAt = Instant.now();
	}

	public TaskStatus getStatus() {
		return status;
	}

	public void setStatus(TaskStatus status) {
		this.status = status;
		this.updatedAt = Instant.now();
	}

	public String getErrorMessage() {
		return errorMessage;
	}

	public void setErrorMessage(String errorMessage) {
		this.errorMessage = errorMessage;
		this.updatedAt = Instant.now();
	}

	public Instant getCreatedAt() {
		return createdAt;
	}

	public Instant getUpdatedAt() {
		return updatedAt;
	}

	public enum TaskStatus {
		QUEUED,
		TRANSCRIBING,
		SUMMARIZING,
		COMPLETED,
		FAILED
	}
}
