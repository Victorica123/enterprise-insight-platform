package com.example.videoplatform.media;

import jakarta.validation.constraints.Min;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotNull;

public final class MediaDtos {

	private MediaDtos() {
	}

	public record SingleUploadResponse(String taskId, String videoId, String storagePath, String status) {
	}

	public record DirectUploadInitRequest(@NotBlank String fileName, @NotNull @Min(1) Long fileSize) {
	}

	public record DirectUploadInitResponse(String uploadUrl, String storagePath, String uploadToken,
			Long expiresAt, String method) {
	}

	public record DirectUploadCompleteRequest(@NotBlank String uploadToken) {
	}

	public record DirectUploadCompleteResponse(String taskId, String videoId, String storagePath, String status) {
	}

	public record InitUploadRequest(
			@NotBlank String fileName,
			@NotNull @Min(1) Long fileSize,
			@NotNull @Min(1) Integer totalChunks,
			@NotNull @Min(1) Integer chunkSize,
			String fileMd5) {
	}

	public record InitUploadResponse(String uploadId, String uploadUrl, Integer totalChunks, Long expiresAt,
			String fileMd5, Boolean exists, java.util.List<Integer> uploadedChunks) {
	}

	public record ChunkUploadResponse(Integer chunkIndex, Integer uploadedChunks, Integer totalChunks) {
	}

	/** 断点续传：查询某个上传会话已完成的分片，前端据此跳过已传分片。 */
	public record UploadStatusResponse(String uploadId, Integer totalChunks, java.util.List<Integer> uploadedChunks,
			Boolean completed) {
	}

	public record MergeRequest(@NotBlank String uploadId) {
	}

	public record MergeResponse(String taskId, String videoId, String storagePath, String status) {
	}

	/** 播放令牌：前端用它拼出可直接喂给 &lt;video&gt; 的带签名播放地址。 */
	public record PlaybackTokenResponse(String token, String streamUrl, Long expiresInSeconds) {
	}
}
