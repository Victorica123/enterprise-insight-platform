package com.example.videoplatform.workflow;

import com.example.videoplatform.transcript.TranscriptResult;
import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.EnumType;
import jakarta.persistence.Enumerated;
import jakarta.persistence.Id;
import jakarta.persistence.Index;
import jakarta.persistence.Table;
import jakarta.persistence.UniqueConstraint;
import java.nio.charset.StandardCharsets;
import java.time.Instant;
import java.util.UUID;

/**
 * Tenant-scoped content-addressed media processing result.
 *
 * <p>The same bytes may be deduplicated inside one workspace, but a content
 * hash from another tenant must never select or mutate this record.  The
 * physical table is suffixed with {@code _scoped} so Hibernate's update mode
 * can introduce the safer schema without changing the primary key of the
 * legacy global cache in place.
 */
@Entity
@Table(name = "media_asset_scoped",
		indexes = {
			@Index(name = "idx_media_asset_scope_status", columnList = "tenantId, status"),
			@Index(name = "idx_media_asset_scope_md5", columnList = "tenantId, contentMd5")
		},
		uniqueConstraints = @UniqueConstraint(
			name = "uk_media_asset_tenant_md5", columnNames = {"tenantId", "contentMd5"}))
public class MediaAsset {

	@Id
	@Column(length = 128)
	private String assetKey;

	@Column(nullable = false, length = 128)
	private String tenantId;

	@Column(nullable = false, length = 64)
	private String contentMd5;

	@Enumerated(EnumType.STRING)
	private AssetStatus status;

	private String storagePath;

	@Column(columnDefinition = "TEXT")
	private String transcript;

	@Column(columnDefinition = "TEXT")
	private String transcriptSegmentsJson;

	private String transcriptLanguage;

	private Long transcriptDurationMs;

	@Column(columnDefinition = "TEXT")
	private String summary;

	@Column(columnDefinition = "TEXT")
	private String errorMessage;

	private Instant createdAt;

	private Instant updatedAt;

	protected MediaAsset() {
		// JPA
	}

	/** Compatibility constructor for legacy fixtures and the legacy workspace. */
	public MediaAsset(String contentMd5, String storagePath) {
		this("legacy", contentMd5, storagePath);
	}

	public MediaAsset(String tenantId, String contentMd5, String storagePath) {
		this.tenantId = normalizeTenantId(tenantId);
		this.contentMd5 = contentMd5;
		this.assetKey = keyFor(this.tenantId, contentMd5);
		this.storagePath = storagePath;
		this.status = AssetStatus.PROCESSING;
		this.createdAt = Instant.now();
		this.updatedAt = this.createdAt;
	}

	public String getAssetKey() {
		return assetKey;
	}

	public String getTenantId() {
		return tenantId;
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

	public void clearStoredMedia() {
		this.storagePath = null;
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

	public void markReady(TranscriptResult transcript, String summary) {
		this.transcript = transcript.text();
		this.transcriptSegmentsJson = transcript.segmentsJson();
		this.transcriptLanguage = transcript.language();
		this.transcriptDurationMs = transcript.durationMs();
		this.summary = summary;
		this.status = AssetStatus.READY;
		this.updatedAt = Instant.now();
	}

	/** Compatibility helper for pre-timestamp unit fixtures and migrated rows. */
	public void markReady(String transcript, String summary) {
		markReady(TranscriptResult.fromPlainText(transcript), summary);
	}

	public TranscriptResult getTranscriptResult() {
		return TranscriptResult.fromStored(transcript, transcriptSegmentsJson, transcriptLanguage, transcriptDurationMs);
	}

	public void expireTranscriptData() {
		this.transcript = null;
		this.transcriptSegmentsJson = null;
		this.transcriptLanguage = null;
		this.transcriptDurationMs = null;
		this.status = AssetStatus.RETENTION_EXPIRED;
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

	static String keyFor(String tenantId, String contentMd5) {
		return UUID.nameUUIDFromBytes(
				(normalizeTenantId(tenantId) + "\u0000" + contentMd5).getBytes(StandardCharsets.UTF_8)).toString();
	}

	private static String normalizeTenantId(String value) {
		return value == null || value.isBlank() ? "legacy" : value.trim();
	}

	public enum AssetStatus {
		PROCESSING,
		READY,
		FAILED,
		RETENTION_EXPIRED
	}
}
