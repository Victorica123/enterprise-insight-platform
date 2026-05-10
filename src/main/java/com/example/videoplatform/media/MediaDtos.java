package com.example.videoplatform.media;

import jakarta.validation.constraints.Min;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotNull;

public final class MediaDtos {

	private MediaDtos() {
	}

	public record SingleUploadResponse(String taskId, String videoId, String storagePath, String status) {
	}

	public record InitUploadRequest(
			@NotBlank String fileName,
			@NotNull @Min(1) Long fileSize,
			@NotNull @Min(1) Integer totalChunks,
			@NotNull @Min(1) Integer chunkSize,
			String fileMd5) {
	}

	public record InitUploadResponse(String uploadId, String uploadUrl, Integer totalChunks, Long expiresAt,
			String fileMd5, Boolean exists) {
	}

	public record ChunkUploadResponse(Integer chunkIndex, Integer uploadedChunks, Integer totalChunks) {
	}

	public record MergeRequest(@NotBlank String uploadId) {
	}

	public record MergeResponse(String taskId, String videoId, String storagePath, String status) {
	}
}
