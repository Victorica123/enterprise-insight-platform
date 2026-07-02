package com.example.videoplatform.workflow;

import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.EnumType;
import jakarta.persistence.Enumerated;
import jakarta.persistence.Id;
import jakarta.persistence.Table;
import java.time.Instant;

/**
 * 内容寻址的媒体资产：按内容指纹（文件 MD5）唯一。
 *
 * <p>把"昂贵的处理结果"（转写 / 摘要）与"用户上传任务"解耦：相同内容（同 MD5）无论被
 * 多少用户、多少次上传，都只处理一次，结果由所有引用它的 {@link VideoTask} 共享。
 * 这是内容级去重的核心——省下的不只是上传带宽，更是分钟级的 FFmpeg / Whisper / LLM 开销。
 */
@Entity
@Table(name = "media_asset")
public class MediaAsset {

	@Id
	private String contentMd5;

	@Enumerated(EnumType.STRING)
	private AssetStatus status;

	private String storagePath;

	@Column(length = 10000)
	private String transcript;

	@Column(length = 5000)
	private String summary;

	@Column(columnDefinition = "TEXT")
	private String errorMessage;

	private Instant createdAt;

	private Instant updatedAt;

	protected MediaAsset() {
		// JPA
	}

	public MediaAsset(String contentMd5, String storagePath) {
		this.contentMd5 = contentMd5;
		this.storagePath = storagePath;
		this.status = AssetStatus.PROCESSING;
		this.createdAt = Instant.now();
		this.updatedAt = this.createdAt;
	}

	public String getContentMd5() {
		return contentMd5;
	}

	public AssetStatus getStatus() {
		return status;
	}

	public void setStatus(AssetStatus status) {
		this.status = status;
		this.updatedAt = Instant.now();
	}

	public String getStoragePath() {
		return storagePath;
	}

	public String getTranscript() {
		return transcript;
	}

	public String getSummary() {
		return summary;
	}

	public String getErrorMessage() {
		return errorMessage;
	}

	public void markReady(String transcript, String summary) {
		this.transcript = transcript;
		this.summary = summary;
		this.status = AssetStatus.READY;
		this.updatedAt = Instant.now();
	}

	public void markFailed(String errorMessage) {
		this.errorMessage = errorMessage;
		this.status = AssetStatus.FAILED;
		this.updatedAt = Instant.now();
	}

	public Instant getCreatedAt() {
		return createdAt;
	}

	public Instant getUpdatedAt() {
		return updatedAt;
	}

	public enum AssetStatus {
		PROCESSING,
		READY,
		FAILED
	}
}
