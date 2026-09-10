package com.example.videoplatform.media;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;
import static org.mockito.ArgumentMatchers.any;
import static org.mockito.ArgumentMatchers.eq;
import static org.mockito.Mockito.never;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.verifyNoInteractions;
import static org.mockito.Mockito.when;

import com.example.videoplatform.config.AppProperties;
import com.example.videoplatform.workflow.DistributedLockService;
import com.example.videoplatform.workflow.VideoTask;
import com.example.videoplatform.workflow.VideoTaskService;
import java.nio.file.Files;
import java.nio.file.Path;
import java.time.Duration;
import java.util.HashMap;
import java.util.Map;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.io.TempDir;
import org.springframework.data.redis.core.HashOperations;
import org.springframework.data.redis.core.SetOperations;
import org.springframework.data.redis.core.StringRedisTemplate;
import org.springframework.data.redis.core.ValueOperations;
import org.springframework.mock.web.MockMultipartFile;

@SuppressWarnings("unchecked")
class ChunkUploadServiceTests {

	@TempDir
	Path storageRoot;

	private final StringRedisTemplate redisTemplate = org.mockito.Mockito.mock(StringRedisTemplate.class);
	private final ValueOperations<String, String> valueOperations = org.mockito.Mockito.mock(ValueOperations.class);
	private final HashOperations<String, Object, Object> hashOperations = org.mockito.Mockito.mock(HashOperations.class);
	private final SetOperations<String, String> setOperations = org.mockito.Mockito.mock(SetOperations.class);
	private final VideoTaskService videoTaskService = org.mockito.Mockito.mock(VideoTaskService.class);
	private final DistributedLockService lockService = org.mockito.Mockito.mock(DistributedLockService.class);
	private ChunkUploadService service;

	@BeforeEach
	void setUp() {
		AppProperties appProperties = new AppProperties();
		appProperties.getStorage().setBasePath(storageRoot.toString());
		when(redisTemplate.opsForValue()).thenReturn(valueOperations);
		when(redisTemplate.opsForHash()).thenReturn(hashOperations);
		when(redisTemplate.opsForSet()).thenReturn(setOperations);
		service = new ChunkUploadService(redisTemplate, appProperties, videoTaskService, lockService,
				new LocalMediaStorageService(appProperties));
	}

	@Test
	void initUploadStoresOwnerAndExpiresMetadata() {
		MediaDtos.InitUploadRequest request = new MediaDtos.InitUploadRequest(
				"demo.mp4", 1024L, 2, 512, "md5-1");
		when(valueOperations.get("file:md5:md5-1")).thenReturn(null);

		MediaDtos.InitUploadResponse response = service.initUpload("alice", request);

		assertThat(response.uploadId()).isNotBlank();
		assertThat(response.uploadUrl()).isEqualTo("/api/media/upload/chunk");
		verify(hashOperations).putAll(eq("upload:" + response.uploadId() + ":meta"), any(Map.class));
		verify(redisTemplate).expire("upload:" + response.uploadId() + ":meta", Duration.ofHours(24));
	}

	@Test
	void initUploadDropsStaleDedupMappingWhenMediaWasDeleted() {
		MediaDtos.InitUploadRequest request = new MediaDtos.InitUploadRequest(
				"demo.mp4", 1024L, 2, 512, "md5-stale");
		when(valueOperations.get("file:md5:md5-stale"))
				.thenReturn(storageRoot.resolve("uploads/missing.mp4").toString());

		MediaDtos.InitUploadResponse response = service.initUpload("alice", request);

		assertThat(response.exists()).isFalse();
		assertThat(response.uploadId()).isNotBlank();
		verify(redisTemplate).delete("file:md5:md5-stale");
		verify(videoTaskService, never()).createTask(any(), any(), any(), any());
	}

	@Test
	void uploadChunkRejectsDifferentOwnerBeforeWritingFile() {
		when(hashOperations.entries("upload:upload-1:meta")).thenReturn(uploadMeta("bob", "2"));
		MockMultipartFile file = new MockMultipartFile("file", "chunk", "application/octet-stream", new byte[] {1});

		assertThatThrownBy(() -> service.uploadChunk("alice", "upload-1", 0, file))
				.isInstanceOf(IllegalArgumentException.class);

		assertThat(storageRoot.resolve("chunks").resolve("upload-1")).doesNotExist();
		verifyNoInteractions(setOperations);
	}

	@Test
	void uploadChunkRejectsOutOfRangeIndex() {
		when(hashOperations.entries("upload:upload-1:meta")).thenReturn(uploadMeta("alice", "2"));
		MockMultipartFile file = new MockMultipartFile("file", "chunk", "application/octet-stream", new byte[] {1});

		assertThatThrownBy(() -> service.uploadChunk("alice", "upload-1", 2, file))
				.isInstanceOf(IllegalArgumentException.class)
				.hasMessageContaining("2");

		assertThat(storageRoot.resolve("chunks").resolve("upload-1")).doesNotExist();
		verifyNoInteractions(setOperations);
	}

	@Test
	void uploadChunkWritesChunkAndRefreshesChunkSetTtl() throws Exception {
		when(hashOperations.entries("upload:upload-1:meta")).thenReturn(uploadMeta("alice", "2"));
		when(setOperations.size("upload:upload-1:chunks")).thenReturn(1L);
		MockMultipartFile file = new MockMultipartFile("file", "chunk", "application/octet-stream", new byte[] {7});

		MediaDtos.ChunkUploadResponse response = service.uploadChunk("alice", "upload-1", 0, file);

		assertThat(response.chunkIndex()).isEqualTo(0);
		assertThat(response.uploadedChunks()).isEqualTo(1);
		assertThat(Files.readAllBytes(storageRoot.resolve("chunks").resolve("upload-1").resolve("0")))
				.containsExactly(7);
		verify(setOperations).add("upload:upload-1:chunks", "0");
		verify(redisTemplate).expire("upload:upload-1:chunks", Duration.ofHours(24));
		verify(redisTemplate).expire("upload:upload-1:meta", Duration.ofHours(24));
	}

	@Test
	void mergeChunksRejectsWhenNotAllChunksUploaded() {
		when(hashOperations.entries("upload:upload-1:meta")).thenReturn(uploadMeta("alice", "2"));
		when(setOperations.size("upload:upload-1:chunks")).thenReturn(1L);

		assertThatThrownBy(() -> service.mergeChunks("alice", new MediaDtos.MergeRequest("upload-1")))
				.isInstanceOf(IllegalArgumentException.class);

		verifyNoInteractions(lockService);
	}

	@Test
	void mergeChunksRejectsWhenLockIsUnavailable() {
		when(hashOperations.entries("upload:upload-1:meta")).thenReturn(uploadMeta("alice", "2"));
		when(setOperations.size("upload:upload-1:chunks")).thenReturn(2L);
		when(lockService.tryLock("lock:merge:upload-1", 30)).thenReturn(false);

		assertThatThrownBy(() -> service.mergeChunks("alice", new MediaDtos.MergeRequest("upload-1")))
				.isInstanceOf(IllegalStateException.class);

		verify(lockService).tryLock("lock:merge:upload-1", 30);
		verify(lockService, never()).unlock("lock:merge:upload-1");
	}

	@Test
	void mergeChunksCreatesTaskPublishesAndCleansState() throws Exception {
		when(hashOperations.entries("upload:upload-1:meta")).thenReturn(uploadMeta("alice", "2"));
		when(setOperations.size("upload:upload-1:chunks")).thenReturn(2L);
		when(lockService.tryLock("lock:merge:upload-1", 30)).thenReturn(true);
		VideoTask task = new VideoTask("task-1", "video-1", "alice", "demo.mp4", "storage/demo.mp4");
		when(videoTaskService.createTask(eq("alice"), eq("demo.mp4"), any(), any())).thenReturn(task);
		Path chunkDir = storageRoot.resolve("chunks").resolve("upload-1");
		Files.createDirectories(chunkDir);
		Files.write(chunkDir.resolve("0"), new byte[] {1, 2});
		Files.write(chunkDir.resolve("1"), new byte[] {3, 4});

		MediaDtos.MergeResponse response = service.mergeChunks("alice", new MediaDtos.MergeRequest("upload-1"));

		assertThat(response.taskId()).isEqualTo("task-1");
		assertThat(response.videoId()).isEqualTo("video-1");
		assertThat(response.status()).isEqualTo("QUEUED");
		assertThat(storageRoot.resolve("chunks").resolve("upload-1")).doesNotExist();
		verify(redisTemplate).delete("upload:upload-1:meta");
		verify(redisTemplate).delete("upload:upload-1:chunks");
		verify(videoTaskService).createTask(eq("alice"), eq("demo.mp4"), any(), any());
		verify(lockService).unlock("lock:merge:upload-1");
	}

	@Test
	void getUploadStatusReturnsSortedUploadedChunks() {
		when(hashOperations.entries("upload:upload-1:meta")).thenReturn(uploadMeta("alice", "3"));
		when(setOperations.members("upload:upload-1:chunks"))
				.thenReturn(new java.util.HashSet<>(java.util.List.of("2", "0")));

		MediaDtos.UploadStatusResponse status = service.getUploadStatus("alice", "upload-1");

		assertThat(status.totalChunks()).isEqualTo(3);
		assertThat(status.uploadedChunks()).containsExactly(0, 2);
		assertThat(status.completed()).isFalse();
	}

	@Test
	void getUploadStatusRejectsDifferentOwner() {
		when(hashOperations.entries("upload:upload-1:meta")).thenReturn(uploadMeta("bob", "2"));

		assertThatThrownBy(() -> service.getUploadStatus("alice", "upload-1"))
				.isInstanceOf(IllegalArgumentException.class);
	}

	@Test
	void initUploadResumesInProgressSessionForSameMd5() {
		MediaDtos.InitUploadRequest request = new MediaDtos.InitUploadRequest("demo.mp4", 1024L, 3, 512, "md5-r");
		when(valueOperations.get("file:md5:md5-r")).thenReturn(null);
		when(valueOperations.get("upload:inprogress:md5-r")).thenReturn("existing-upload");
		when(hashOperations.entries("upload:existing-upload:meta")).thenReturn(uploadMeta("alice", "3"));
		when(setOperations.members("upload:existing-upload:chunks"))
				.thenReturn(new java.util.HashSet<>(java.util.List.of("0", "1")));

		MediaDtos.InitUploadResponse response = service.initUpload("alice", request);

		assertThat(response.uploadId()).isEqualTo("existing-upload");
		assertThat(response.exists()).isFalse();
		assertThat(response.uploadedChunks()).containsExactly(0, 1);
		// 复用会话，不应再创建新会话
		verify(hashOperations, never()).putAll(any(), any());
	}

	@Test
	void mergeChunksFailsIntegrityCheckAndCleansUpOnMd5Mismatch() throws Exception {
		Map<Object, Object> meta = uploadMeta("alice", "2");
		meta.put("fileMd5", "deadbeefdeadbeefdeadbeefdeadbeef");
		when(hashOperations.entries("upload:upload-1:meta")).thenReturn(meta);
		when(setOperations.size("upload:upload-1:chunks")).thenReturn(2L);
		when(lockService.tryLock("lock:merge:upload-1", 30)).thenReturn(true);
		Path chunkDir = storageRoot.resolve("chunks").resolve("upload-1");
		Files.createDirectories(chunkDir);
		Files.write(chunkDir.resolve("0"), new byte[] {1, 2});
		Files.write(chunkDir.resolve("1"), new byte[] {3, 4});

		assertThatThrownBy(() -> service.mergeChunks("alice", new MediaDtos.MergeRequest("upload-1")))
				.isInstanceOf(IllegalArgumentException.class)
				.hasMessageContaining("完整性校验失败");

		// 校验失败的半成品文件必须清理，且不创建任务
		Path uploads = storageRoot.resolve("uploads");
		if (Files.exists(uploads)) {
			try (var stream = Files.list(uploads)) {
				assertThat(stream.findAny()).isEmpty();
			}
		} else {
			assertThat(uploads).doesNotExist();
		}
		verify(videoTaskService, never()).createTask(any(), any(), any(), any());
		verify(lockService).unlock("lock:merge:upload-1");
	}

	@Test
	void mergeChunksPassesIntegrityCheckOnMatchingMd5() throws Exception {
		String md5 = md5Hex(new byte[] {1, 2, 3, 4});
		Map<Object, Object> meta = uploadMeta("alice", "2");
		meta.put("fileMd5", md5);
		when(hashOperations.entries("upload:upload-1:meta")).thenReturn(meta);
		when(setOperations.size("upload:upload-1:chunks")).thenReturn(2L);
		when(lockService.tryLock("lock:merge:upload-1", 30)).thenReturn(true);
		VideoTask task = new VideoTask("task-1", "video-1", "alice", "demo.mp4", "storage/demo.mp4");
		when(videoTaskService.createTask(eq("alice"), eq("demo.mp4"), any(), any())).thenReturn(task);
		Path chunkDir = storageRoot.resolve("chunks").resolve("upload-1");
		Files.createDirectories(chunkDir);
		Files.write(chunkDir.resolve("0"), new byte[] {1, 2});
		Files.write(chunkDir.resolve("1"), new byte[] {3, 4});

		MediaDtos.MergeResponse response = service.mergeChunks("alice", new MediaDtos.MergeRequest("upload-1"));

		assertThat(response.taskId()).isEqualTo("task-1");
		verify(redisTemplate).delete("upload:inprogress:" + md5);
	}

	private static String md5Hex(byte[] data) throws Exception {
		byte[] digest = java.security.MessageDigest.getInstance("MD5").digest(data);
		StringBuilder sb = new StringBuilder();
		for (byte b : digest) {
			sb.append(Character.forDigit((b >> 4) & 0xF, 16));
			sb.append(Character.forDigit(b & 0xF, 16));
		}
		return sb.toString();
	}

	private static Map<Object, Object> uploadMeta(String owner, String totalChunks) {
		Map<Object, Object> meta = new HashMap<>();
		meta.put("owner", owner);
		meta.put("fileName", "demo.mp4");
		meta.put("totalChunks", totalChunks);
		return meta;
	}
}
