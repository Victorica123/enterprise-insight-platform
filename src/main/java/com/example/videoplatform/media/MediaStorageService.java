package com.example.videoplatform.media;

import java.io.IOException;
import java.io.InputStream;
import java.nio.file.Path;
import java.time.Duration;
import java.time.Instant;
import java.util.Optional;

/**
 * 媒体文件存储边界。默认实现是本地磁盘；生产可切到 S3/MinIO 兼容对象存储。
 *
 * <p>工作流仍需要 FFmpeg 读取本地文件，因此对象存储实现会在处理阶段下载到临时文件，
 * 播放阶段则返回预签名 URL，让对象存储处理 Range 请求和大文件传输。
 */
public interface MediaStorageService {

	String saveUpload(String safeFileName, InputStream inputStream) throws IOException;

	String saveFile(String safeFileName, Path sourceFile) throws IOException;

	DirectUploadTarget createDirectUploadTarget(String safeFileName, Duration expiresIn);

	boolean objectExists(String storagePath) throws IOException;

	void delete(String storagePath) throws IOException;

	ResolvedMedia resolveForProcessing(String storagePath) throws IOException;

	Optional<String> createPlaybackRedirectUrl(String storagePath, Duration expiresIn);

	Path requireLocalPath(String storagePath);

	record DirectUploadTarget(String storagePath, String uploadUrl, Instant expiresAt) {
	}

	record ResolvedMedia(Path localPath, boolean temporary) implements AutoCloseable {
		@Override
		public void close() throws IOException {
			if (temporary) {
				java.nio.file.Files.deleteIfExists(localPath);
			}
		}
	}
}
