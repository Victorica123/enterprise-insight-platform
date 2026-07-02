package com.example.videoplatform.workflow;

import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.EnumType;
import jakarta.persistence.Enumerated;
import jakarta.persistence.Id;
import jakarta.persistence.Table;
import java.time.Instant;

@Entity
@Table(name = "video_task")
public class VideoTask {

	@Id
	private String taskId;

	private String videoId;

	private String owner;

	private String fileName;

	private String storagePath;

	/** 内容指纹（文件 MD5）。用于内容级去重与单飞处理；单文件上传等无指纹场景可为 null。 */
	private String contentMd5;

	@Column(columnDefinition = "TEXT")
	private String transcript;

	@Column(columnDefinition = "TEXT")
	private String summary;

	@Enumerated(EnumType.STRING)
	private TaskStatus status;

	@Column(columnDefinition = "TEXT")
	private String errorMessage;

	private Instant createdAt;

	private Instant updatedAt;

	protected VideoTask() {
		// JPA requires no-arg constructor
	}

	public VideoTask(String taskId, String videoId, String owner, String fileName, String storagePath) {
		this(taskId, videoId, owner, fileName, storagePath, null);
	}

	public VideoTask(String taskId, String videoId, String owner, String fileName, String storagePath,
			String contentMd5) {
		this.taskId = taskId;
		this.videoId = videoId;
		this.owner = owner;
		this.fileName = fileName;
		this.storagePath = storagePath;
		this.contentMd5 = contentMd5;
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

	public String getContentMd5() {
		return contentMd5;
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
