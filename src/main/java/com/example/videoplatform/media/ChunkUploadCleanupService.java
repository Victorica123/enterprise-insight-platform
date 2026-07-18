package com.example.videoplatform.media;

import com.example.videoplatform.config.AppProperties;
import io.micrometer.core.instrument.MeterRegistry;
import java.io.IOException;
import java.nio.file.Files;
import java.nio.file.LinkOption;
import java.nio.file.Path;
import java.nio.file.attribute.FileTime;
import java.time.Instant;
import java.util.Comparator;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.scheduling.annotation.Scheduled;
import org.springframework.stereotype.Service;

/** Removes expired chunk directories left behind after interrupted uploads or expired Redis sessions. */
@Service
public class ChunkUploadCleanupService {

	private static final Logger log = LoggerFactory.getLogger(ChunkUploadCleanupService.class);

	private final AppProperties appProperties;
	private final MeterRegistry meterRegistry;

	public ChunkUploadCleanupService(AppProperties appProperties, MeterRegistry meterRegistry) {
		this.appProperties = appProperties;
		this.meterRegistry = meterRegistry;
	}

	@Scheduled(
			fixedDelayString = "${app.storage.cleanup.chunk-scan-interval-ms:600000}",
			initialDelayString = "${app.storage.cleanup.chunk-scan-initial-delay-ms:60000}")
	public CleanupReport cleanupExpiredChunks() {
		Path root = Path.of(appProperties.getStorage().getBasePath()).toAbsolutePath().normalize().resolve("chunks");
		if (!Files.isDirectory(root, LinkOption.NOFOLLOW_LINKS)) {
			return new CleanupReport(0, 0, 0);
		}

		Instant cutoff = Instant.now().minus(appProperties.getStorage().getCleanup().getChunkRetention());
		int scanned = 0;
		int deleted = 0;
		int failed = 0;
		try (var children = Files.list(root)) {
			for (Path candidate : children.toList()) {
				if (!isSafeSessionDirectory(root, candidate)) {
					continue;
				}
				scanned++;
				try {
					if (latestModified(candidate).toInstant().isBefore(cutoff)) {
						deleteTree(candidate);
						deleted++;
						meterRegistry.counter("video.upload.chunk.cleanup", "result", "deleted").increment();
					}
				} catch (IOException exception) {
					failed++;
					meterRegistry.counter("video.upload.chunk.cleanup", "result", "failed").increment();
					log.warn("Failed to clean expired chunk session {}: {}", candidate.getFileName(), exception.getMessage());
				}
			}
		} catch (IOException exception) {
			log.warn("Failed to scan chunk upload directory {}: {}", root, exception.getMessage());
			return new CleanupReport(scanned, deleted, failed + 1);
		}

		if (deleted > 0 || failed > 0) {
			log.info("Chunk cleanup finished: scanned={}, deleted={}, failed={}", scanned, deleted, failed);
		}
		return new CleanupReport(scanned, deleted, failed);
	}

	private static boolean isSafeSessionDirectory(Path root, Path candidate) {
		Path normalized = candidate.toAbsolutePath().normalize();
		return normalized.getParent() != null
				&& normalized.getParent().equals(root)
				&& Files.isDirectory(normalized, LinkOption.NOFOLLOW_LINKS)
				&& !Files.isSymbolicLink(normalized);
	}

	private static FileTime latestModified(Path directory) throws IOException {
		FileTime latest = Files.getLastModifiedTime(directory, LinkOption.NOFOLLOW_LINKS);
		try (var paths = Files.walk(directory)) {
			for (Path path : paths.toList()) {
				FileTime modified = Files.getLastModifiedTime(path, LinkOption.NOFOLLOW_LINKS);
				if (modified.compareTo(latest) > 0) {
					latest = modified;
				}
			}
		}
		return latest;
	}

	private static void deleteTree(Path directory) throws IOException {
		try (var paths = Files.walk(directory)) {
			for (Path path : paths.sorted(Comparator.reverseOrder()).toList()) {
				Files.deleteIfExists(path);
			}
		}
	}

	public record CleanupReport(int scanned, int deleted, int failed) {
	}
}
