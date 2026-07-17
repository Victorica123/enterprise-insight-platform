package com.example.videoplatform.media;

import com.example.videoplatform.config.AppProperties;
import com.example.videoplatform.workflow.DistributedLockService;
import com.example.videoplatform.workflow.VideoTask;
import com.example.videoplatform.workflow.VideoTaskService;
import com.example.videoplatform.workflow.WorkflowPublisher;
import java.io.IOException;
import java.io.InputStream;
import java.io.OutputStream;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.StandardCopyOption;
import java.nio.file.StandardOpenOption;
import java.time.Duration;
import java.time.Instant;
import java.util.Map;
import java.util.UUID;
import java.util.stream.Collectors;
import org.springframework.boot.autoconfigure.condition.ConditionalOnProperty;
import org.springframework.data.redis.core.StringRedisTemplate;
import org.springframework.stereotype.Service;
import org.springframework.web.multipart.MultipartFile;

@Service
@ConditionalOnProperty(prefix = "app.redis", name = "enabled", havingValue = "true")
public class ChunkUploadService {

	private static final String UPLOAD_META_KEY = "upload:%s:meta";
	private static final String UPLOAD_CHUNKS_KEY = "upload:%s:chunks";
	private static final String LOCK_MERGE_KEY = "lock:merge:%s";
	private static final String FILE_MD5_KEY = "file:md5:%s";
	// 断点续传：文件 MD5 → 进行中的 uploadId，使刷新页面后仍能找回未完成的会话。
	private static final String INPROGRESS_MD5_KEY = "upload:inprogress:%s";

	private final StringRedisTemplate redisTemplate;
	private final AppProperties appProperties;
	private final VideoTaskService videoTaskService;
	private final WorkflowPublisher workflowPublisher;
	private final DistributedLockService lockService;
	private final MediaStorageService mediaStorageService;

	public ChunkUploadService(StringRedisTemplate redisTemplate, AppProperties appProperties,
			VideoTaskService videoTaskService, WorkflowPublisher workflowPublisher,
			DistributedLockService lockService, MediaStorageService mediaStorageService) {
		this.redisTemplate = redisTemplate;
		this.appProperties = appProperties;
		this.videoTaskService = videoTaskService;
		this.workflowPublisher = workflowPublisher;
		this.lockService = lockService;
		this.mediaStorageService = mediaStorageService;
	}

	public MediaDtos.InitUploadResponse initUpload(String owner, MediaDtos.InitUploadRequest request) {
		String safeName = MediaFileValidator.safeVideoFileName(request.fileName());
		String fileMd5 = request.fileMd5();
		if (fileMd5 != null && !fileMd5.isBlank()) {
			String existingPath = redisTemplate.opsForValue().get(String.format(FILE_MD5_KEY, fileMd5));
			if (existingPath != null) {
				VideoTask task = videoTaskService.createTask(owner, safeName, existingPath, fileMd5);
				workflowPublisher.publish(task.getTaskId());
				return new MediaDtos.InitUploadResponse(
						task.getTaskId(), null, request.totalChunks(), null, fileMd5, true, java.util.List.of());
			}

			// 断点续传：同一文件（相同 MD5）存在未完成的会话时，复用它并回传已上传分片，
			// 让前端跳过已传部分。刷新页面 / 断网重连都能续传。
			MediaDtos.InitUploadResponse resumed = tryResume(owner, fileMd5);
			if (resumed != null) {
				return resumed;
			}
		}

		String uploadId = UUID.randomUUID().toString();
		String metaKey = String.format(UPLOAD_META_KEY, uploadId);

		java.util.HashMap<String, String> meta = new java.util.HashMap<>();
		meta.put("fileName", safeName);
		meta.put("fileSize", String.valueOf(request.fileSize()));
		meta.put("totalChunks", String.valueOf(request.totalChunks()));
		meta.put("chunkSize", String.valueOf(request.chunkSize()));
		meta.put("owner", owner);
		meta.put("createdAt", String.valueOf(Instant.now().toEpochMilli()));
		if (fileMd5 != null && !fileMd5.isBlank()) {
			meta.put("fileMd5", fileMd5);
		}

		redisTemplate.opsForHash().putAll(metaKey, meta);
		redisTemplate.expire(metaKey, Duration.ofHours(24));
		if (fileMd5 != null && !fileMd5.isBlank()) {
			redisTemplate.opsForValue().set(String.format(INPROGRESS_MD5_KEY, fileMd5), uploadId, Duration.ofHours(24));
		}

		return new MediaDtos.InitUploadResponse(uploadId, "/api/media/upload/chunk", request.totalChunks(),
				Instant.now().plusSeconds(86400).toEpochMilli(), fileMd5, false, java.util.List.of());
	}

	/**
	 * 若该 MD5 存在归属于 owner 的未完成会话，返回复用响应（含已上传分片）；否则返回 null。
	 * 会话已过期或属于他人时，清理悬空映射并当作新会话处理。
	 */
	private MediaDtos.InitUploadResponse tryResume(String owner, String fileMd5) {
		String inprogressKey = String.format(INPROGRESS_MD5_KEY, fileMd5);
		String existingUploadId = redisTemplate.opsForValue().get(inprogressKey);
		if (existingUploadId == null) {
			return null;
		}
		Map<Object, Object> meta = redisTemplate.opsForHash().entries(String.format(UPLOAD_META_KEY, existingUploadId));
		if (meta == null || meta.isEmpty() || !owner.equals(meta.get("owner"))) {
			redisTemplate.delete(inprogressKey);
			return null;
		}
		int totalChunks = Integer.parseInt((String) meta.get("totalChunks"));
		return new MediaDtos.InitUploadResponse(existingUploadId, "/api/media/upload/chunk", totalChunks, null,
				fileMd5, false, uploadedChunks(existingUploadId));
	}

	/** 断点续传状态查询：返回该会话已完成的分片索引（升序）。 */
	public MediaDtos.UploadStatusResponse getUploadStatus(String owner, String uploadId) {
		String metaKey = String.format(UPLOAD_META_KEY, uploadId);
		Map<Object, Object> meta = redisTemplate.opsForHash().entries(metaKey);
		if (meta == null || meta.isEmpty()) {
			throw new IllegalArgumentException("上传会话不存在或已过期: " + uploadId);
		}
		requireUploadOwner(meta, owner);
		int totalChunks = Integer.parseInt((String) meta.get("totalChunks"));
		java.util.List<Integer> uploaded = uploadedChunks(uploadId);
		return new MediaDtos.UploadStatusResponse(uploadId, totalChunks, uploaded, uploaded.size() >= totalChunks);
	}

	private java.util.List<Integer> uploadedChunks(String uploadId) {
		java.util.Set<String> members = redisTemplate.opsForSet().members(String.format(UPLOAD_CHUNKS_KEY, uploadId));
		if (members == null || members.isEmpty()) {
			return java.util.List.of();
		}
		return members.stream().map(Integer::parseInt).sorted().collect(Collectors.toList());
	}

	public MediaDtos.ChunkUploadResponse uploadChunk(String owner, String uploadId, int chunkIndex, MultipartFile file) {
		if (file == null || file.isEmpty()) {
			throw new IllegalArgumentException("分片文件不能为空");
		}

		String metaKey = String.format(UPLOAD_META_KEY, uploadId);
		Map<Object, Object> meta = redisTemplate.opsForHash().entries(metaKey);
		if (meta == null || meta.isEmpty()) {
			throw new IllegalArgumentException("上传会话不存在或已过期: " + uploadId);
		}
		requireUploadOwner(meta, owner);

		int totalChunks = Integer.parseInt((String) meta.get("totalChunks"));
		if (chunkIndex < 0 || chunkIndex >= totalChunks) {
			throw new IllegalArgumentException("分片索引越界: " + chunkIndex);
		}

		try {
			Path chunkDir = Path.of(appProperties.getStorage().getBasePath())
					.resolve("chunks")
					.resolve(uploadId);
			Files.createDirectories(chunkDir);
			Path chunkPath = chunkDir.resolve(String.valueOf(chunkIndex));
			try (InputStream inputStream = file.getInputStream()) {
				Files.copy(inputStream, chunkPath, StandardCopyOption.REPLACE_EXISTING);
			}
		} catch (IOException e) {
			throw new IllegalStateException("保存分片失败", e);
		}

		String chunksKey = String.format(UPLOAD_CHUNKS_KEY, uploadId);
		redisTemplate.opsForSet().add(chunksKey, String.valueOf(chunkIndex));
		redisTemplate.expire(chunksKey, Duration.ofHours(24));
		Long uploaded = redisTemplate.opsForSet().size(chunksKey);
		return new MediaDtos.ChunkUploadResponse(chunkIndex, uploaded != null ? uploaded.intValue() : 0,
				totalChunks);
	}

	public MediaDtos.MergeResponse mergeChunks(String owner, MediaDtos.MergeRequest request) {
		String uploadId = request.uploadId();
		String metaKey = String.format(UPLOAD_META_KEY, uploadId);
		Map<Object, Object> meta = redisTemplate.opsForHash().entries(metaKey);
		if (meta == null || meta.isEmpty()) {
			throw new IllegalArgumentException("上传会话不存在或已过期: " + uploadId);
		}
		requireUploadOwner(meta, owner);

		int totalChunks = Integer.parseInt((String) meta.get("totalChunks"));
		String fileName = (String) meta.get("fileName");
		String fileMd5 = (String) meta.get("fileMd5");

		String chunksKey = String.format(UPLOAD_CHUNKS_KEY, uploadId);
		Long uploadedCount = redisTemplate.opsForSet().size(chunksKey);
		if (uploadedCount == null || uploadedCount.intValue() < totalChunks) {
			throw new IllegalArgumentException(
					"分片未全部上传，已上传 " + (uploadedCount != null ? uploadedCount.intValue() : 0) + "/" + totalChunks);
		}

		String lockKey = String.format(LOCK_MERGE_KEY, uploadId);
		boolean locked = lockService.tryLock(lockKey, 30);
		if (!locked) {
			throw new IllegalStateException("合并操作正在进行中，请勿重复提交");
		}

		try {
			String safeName = MediaFileValidator.safeVideoFileName(fileName);
			Path mergeTemp = Files.createTempFile("video-platform-merge-", "-" + safeName);

			try (OutputStream outputStream = Files.newOutputStream(mergeTemp, StandardOpenOption.CREATE,
					StandardOpenOption.TRUNCATE_EXISTING, StandardOpenOption.WRITE)) {
				for (int i = 0; i < totalChunks; i++) {
					Path chunkPath = Path.of(appProperties.getStorage().getBasePath())
							.resolve("chunks")
							.resolve(uploadId)
							.resolve(String.valueOf(i));
					if (!Files.exists(chunkPath)) {
						throw new IllegalStateException("分片文件缺失: " + i);
					}
					Files.copy(chunkPath, outputStream);
				}
			} catch (IOException | RuntimeException e) {
				// 合并中途失败（分片缺失、磁盘异常等）时清理半成品文件，避免残留不完整视频占用磁盘。
				deleteQuietly(mergeTemp);
				throw e;
			}

			// 完整性校验：合并后按整文件 MD5 比对，防止分片丢失/损坏/乱序导致的静默损坏。
			if (fileMd5 != null && !fileMd5.isBlank()) {
				String actualMd5 = computeMd5(mergeTemp);
				if (!fileMd5.equalsIgnoreCase(actualMd5)) {
					deleteQuietly(mergeTemp);
					throw new IllegalArgumentException(
							"文件完整性校验失败：期望 MD5=" + fileMd5 + "，实际=" + actualMd5 + "，请重新上传");
				}
			}

			String stored = mediaStorageService.saveFile(safeName, mergeTemp);
			deleteQuietly(mergeTemp);

			// 清理分片文件
			Path chunkDir = Path.of(appProperties.getStorage().getBasePath())
					.resolve("chunks")
					.resolve(uploadId);
			deleteDirectory(chunkDir);

			// 清理 Redis
			redisTemplate.delete(metaKey);
			redisTemplate.delete(chunksKey);

			// 记录 MD5 映射（如有）
			if (fileMd5 != null && !fileMd5.isBlank()) {
				redisTemplate.opsForValue().set(String.format(FILE_MD5_KEY, fileMd5), stored, Duration.ofDays(7));
				redisTemplate.delete(String.format(INPROGRESS_MD5_KEY, fileMd5));
			}

			VideoTask task = videoTaskService.createTask(owner, safeName, stored, fileMd5);
			workflowPublisher.publish(task.getTaskId());
			return new MediaDtos.MergeResponse(task.getTaskId(), task.getVideoId(), task.getStoragePath(),
					task.getStatus().name());
		} catch (IOException e) {
			throw new IllegalStateException("合并文件失败", e);
		} finally {
			lockService.unlock(lockKey);
		}
	}

	private void deleteDirectory(Path directory) throws IOException {
		if (!Files.exists(directory)) {
			return;
		}
		try (var stream = Files.list(directory)) {
			var files = stream.collect(Collectors.toList());
			for (Path file : files) {
				Files.deleteIfExists(file);
			}
		}
		Files.deleteIfExists(directory);
	}

	private static void deleteQuietly(Path path) {
		try {
			Files.deleteIfExists(path);
		} catch (IOException ignored) {
			// Best effort cleanup.
		}
	}

	/** 计算文件 MD5（十六进制小写），用于合并后的完整性校验。流式读取，避免大文件占用内存。 */
	private static String computeMd5(Path path) {
		try {
			java.security.MessageDigest digest = java.security.MessageDigest.getInstance("MD5");
			byte[] buffer = new byte[8192];
			try (InputStream in = Files.newInputStream(path)) {
				int read;
				while ((read = in.read(buffer)) != -1) {
					digest.update(buffer, 0, read);
				}
			}
			StringBuilder sb = new StringBuilder();
			for (byte b : digest.digest()) {
				sb.append(Character.forDigit((b >> 4) & 0xF, 16));
				sb.append(Character.forDigit(b & 0xF, 16));
			}
			return sb.toString();
		} catch (java.security.NoSuchAlgorithmException | IOException e) {
			throw new IllegalStateException("计算文件 MD5 失败", e);
		}
	}

	private static void requireUploadOwner(Map<Object, Object> meta, String owner) {
		Object uploadOwner = meta.get("owner");
		if (uploadOwner == null || !uploadOwner.equals(owner)) {
			throw new IllegalArgumentException("上传会话不存在或无权限访问");
		}
	}
}
