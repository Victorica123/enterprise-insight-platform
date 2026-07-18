package com.example.videoplatform.media;

import static org.assertj.core.api.Assertions.assertThat;

import com.example.videoplatform.config.AppProperties;
import io.micrometer.core.instrument.simple.SimpleMeterRegistry;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.attribute.FileTime;
import java.time.Duration;
import java.time.Instant;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.io.TempDir;

class ChunkUploadCleanupServiceTests {

	@TempDir
	Path tempDir;

	@Test
	void removesOnlyExpiredChunkSessions() throws Exception {
		Path chunks = Files.createDirectories(tempDir.resolve("chunks"));
		Path expired = createSession(chunks, "expired", Instant.now().minus(Duration.ofHours(30)));
		Path active = createSession(chunks, "active", Instant.now());
		Files.writeString(chunks.resolve("not-a-session.txt"), "keep");

		AppProperties properties = new AppProperties();
		properties.getStorage().setBasePath(tempDir.toString());
		properties.getStorage().getCleanup().setChunkRetention(Duration.ofHours(24));
		SimpleMeterRegistry registry = new SimpleMeterRegistry();
		ChunkUploadCleanupService service = new ChunkUploadCleanupService(properties, registry);

		ChunkUploadCleanupService.CleanupReport report = service.cleanupExpiredChunks();

		assertThat(report.scanned()).isEqualTo(2);
		assertThat(report.deleted()).isEqualTo(1);
		assertThat(report.failed()).isZero();
		assertThat(expired).doesNotExist();
		assertThat(active).exists();
		assertThat(chunks.resolve("not-a-session.txt")).exists();
		assertThat(registry.counter("video.upload.chunk.cleanup", "result", "deleted").count()).isEqualTo(1);
	}

	private static Path createSession(Path chunks, String id, Instant modifiedAt) throws Exception {
		Path directory = Files.createDirectory(chunks.resolve(id));
		Path chunk = Files.writeString(directory.resolve("0"), "data");
		FileTime modified = FileTime.from(modifiedAt);
		Files.setLastModifiedTime(chunk, modified);
		Files.setLastModifiedTime(directory, modified);
		return directory;
	}
}
