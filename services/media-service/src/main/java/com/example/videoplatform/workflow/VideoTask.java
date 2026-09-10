package com.example.videoplatform.workflow;

import com.example.videoplatform.transcript.TranscriptResult;
import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.EnumType;
import jakarta.persistence.Enumerated;
import jakarta.persistence.Id;
import jakarta.persistence.Index;
import jakarta.persistence.Table;
import java.time.Instant;

@Entity
// 索引与真实查询路径一一对应（避免“建了但用不上”的装饰性索引）：
// - (owner, createdAt)：我的视频列表 findByOwnerOrderByCreatedAtDesc
// - (status, updatedAt)：legacy stale-task fallback in the workflow reaper
// - (status, processingLeaseExpiresAt)：leased-task recovery lookup
// - (contentMd5)：tenant-scoped 去重/单飞 fan-out findByTenantIdAndContentMd5
@Table(name = "video_task", indexes = {
		@Index(name = "idx_video_task_owner_created", columnList = "owner, createdAt"),
		@Index(name = "idx_video_task_tenant_owner_created", columnList = "tenantId, owner, createdAt"),
		@Index(name = "idx_video_task_status_updated", columnList = "status, updatedAt"),
		@Index(name = "idx_video_task_content_md5", columnList = "contentMd5"),
		@Index(name = "idx_video_task_lease", columnList = "status, processingLeaseExpiresAt")
})
public class VideoTask {

	@Id
	private String taskId;

	private String videoId;

	private String owner;

	private String tenantId;

	private String traceId;

	private String fileName;

	private String storagePath;

	/** 内容指纹（文件 MD5）。用于内容级去重与单飞处理；单文件上传等无指纹场景可为 null。 */
	private String contentMd5;

	/** Fencing token for the worker currently processing this task. */
	private String processingLeaseId;

	/** Lease expiry used by the reaper; old rows with null use updatedAt fallback. */
	private Instant processingLeaseExpiresAt;

	@Column(columnDefinition = "TEXT")
	private String transcript;

	@Column(columnDefinition = "TEXT")
	private String transcriptSegmentsJson;

	private String transcriptLanguage;

	private Long transcriptDurationMs;

	private int transcriptVersion = 1;

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
		this(taskId, videoId, "legacy", owner, fileName, storagePath, contentMd5, taskId);
	}

	public VideoTask(String taskId, String videoId, String tenantId, String owner, String fileName,
			String storagePath, String contentMd5, String traceId) {
		this.taskId = taskId;
		this.videoId = videoId;
		this.tenantId = tenantId;
		this.owner = owner;
		this.traceId = traceId;
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

	public String getTenantId() {
		return tenantId == null || tenantId.isBlank() ? "legacy" : tenantId;
	}

	public String getTraceId() {
		return traceId == null || traceId.isBlank() ? taskId : traceId;
	}

	public String getFileName() {
		return fileName;
	}

	public String getStoragePath() {
		return storagePath;
	}

	public void clearStoredMedia() {
		this.storagePath = null;
	}

	public String getContentMd5() {
		return contentMd5;
	}

	public String getProcessingLeaseId() {
		return processingLeaseId;
	}

	public Instant getProcessingLeaseExpiresAt() {
		return processingLeaseExpiresAt;
	}

	public void setProcessingLease(String leaseId, Instant expiresAt) {
		this.processingLeaseId = leaseId;
		this.processingLeaseExpiresAt = expiresAt;
		this.updatedAt = Instant.now();
	}

	public void clearProcessingLease() {
		this.processingLeaseId = null;
		this.processingLeaseExpiresAt = null;
		this.updatedAt = Instant.now();
	}

	public String getTranscript() {
		return transcript;
	}

	public void setTranscript(String transcript) {
		this.transcript = transcript;
		this.updatedAt = Instant.now();
	}

	public void setTranscriptResult(TranscriptResult result) {
		this.transcript = result.text();
		this.transcriptSegmentsJson = result.segmentsJson();
		this.transcriptLanguage = result.language();
		this.transcriptDurationMs = result.durationMs();
		this.transcriptVersion = 1;
		this.updatedAt = Instant.now();
	}

	public TranscriptResult getTranscriptResult() {
		return TranscriptResult.fromStored(transcript, transcriptSegmentsJson, transcriptLanguage, transcriptDurationMs);
	}

	public void clearTranscriptData() {
		this.transcript = null;
		this.transcriptSegmentsJson = null;
		this.transcriptLanguage = null;
		this.transcriptDurationMs = null;
	}

	public int getTranscriptVersion() {
		return transcriptVersion <= 0 ? 1 : transcriptVersion;
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
