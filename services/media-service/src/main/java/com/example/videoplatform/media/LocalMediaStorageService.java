package com.example.videoplatform.media;

import com.example.videoplatform.config.AppProperties;
import java.io.IOException;
import java.io.InputStream;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.StandardCopyOption;
import java.time.Duration;
import java.util.Optional;
import java.util.UUID;
import org.springframework.boot.autoconfigure.condition.ConditionalOnProperty;
import org.springframework.http.HttpStatus;
import org.springframework.stereotype.Service;
import org.springframework.web.server.ResponseStatusException;

@Service
@ConditionalOnProperty(prefix = "app.storage", name = "type", havingValue = "local", matchIfMissing = true)
public class LocalMediaStorageService implements MediaStorageService {

	private final AppProperties appProperties;

	public LocalMediaStorageService(AppProperties appProperties) {
		this.appProperties = appProperties;
	}

	@Override
	public String saveUpload(String safeFileName, InputStream inputStream) throws IOException {
		Path stored = newStoredPath(safeFileName);
		Files.copy(inputStream, stored, StandardCopyOption.REPLACE_EXISTING);
		return stored.toString();
	}

	@Override
	public String saveFile(String safeFileName, Path sourceFile) throws IOException {
		Path stored = newStoredPath(safeFileName);
		Files.copy(sourceFile, stored, StandardCopyOption.REPLACE_EXISTING);
		return stored.toString();
	}

	@Override
	public DirectUploadTarget createDirectUploadTarget(String safeFileName, Duration expiresIn) {
		// 与分片上传（Redis 关闭时返回 503）保持一致的语义：直传能力不可用而非服务器内部错误，
		// 前端据此可优雅降级到普通/分片上传，而不是收到通用 500。
		throw new ResponseStatusException(HttpStatus.SERVICE_UNAVAILABLE,
				"浏览器直传需要对象存储模式（app.storage.type=s3）");
	}

	@Override
	public boolean objectExists(String storagePath) {
		return Files.isRegularFile(Path.of(storagePath));
	}

	@Override
	public void delete(String storagePath) throws IOException {
		Files.deleteIfExists(Path.of(storagePath));
	}

	@Override
	public ResolvedMedia resolveForProcessing(String storagePath) {
		return new ResolvedMedia(Path.of(storagePath), false);
	}

	@Override
	public Optional<String> createPlaybackRedirectUrl(String storagePath, Duration expiresIn) {
		return Optional.empty();
	}

	@Override
	public Path requireLocalPath(String storagePath) {
		return Path.of(storagePath);
	}

	private Path newStoredPath(String safeFileName) throws IOException {
		Path baseDir = Path.of(appProperties.getStorage().getBasePath()).resolve("uploads");
		Files.createDirectories(baseDir);
		return baseDir.resolve(UUID.randomUUID() + "-" + safeFileName);
	}
}
