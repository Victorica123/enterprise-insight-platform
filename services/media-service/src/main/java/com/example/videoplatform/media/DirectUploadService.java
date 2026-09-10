package com.example.videoplatform.media;

import com.example.videoplatform.auth.JwtService;
import com.example.videoplatform.workflow.VideoTask;
import com.example.videoplatform.workflow.VideoTaskService;
import io.jsonwebtoken.Claims;
import java.io.IOException;
import java.time.Duration;
import org.springframework.http.HttpStatus;
import org.springframework.stereotype.Service;
import org.springframework.web.server.ResponseStatusException;

@Service
public class DirectUploadService {

	private final MediaStorageService mediaStorageService;
	private final JwtService jwtService;
	private final VideoTaskService videoTaskService;

	public DirectUploadService(MediaStorageService mediaStorageService, JwtService jwtService,
			VideoTaskService videoTaskService) {
		this.mediaStorageService = mediaStorageService;
		this.jwtService = jwtService;
		this.videoTaskService = videoTaskService;
	}

	public MediaDtos.DirectUploadInitResponse initDirectUpload(String owner,
			MediaDtos.DirectUploadInitRequest request) {
		return initDirectUpload(owner, "legacy", request);
	}

	public MediaDtos.DirectUploadInitResponse initDirectUpload(String owner, String tenantId,
			MediaDtos.DirectUploadInitRequest request) {
		videoTaskService.assertCanCreateTask(owner);
		String safeName = MediaFileValidator.safeVideoFileName(request.fileName());
		Duration expiresIn = Duration.ofSeconds(jwtService.getDirectUploadTokenSeconds());
		MediaStorageService.DirectUploadTarget target;
		try {
			target = mediaStorageService.createDirectUploadTarget(safeName, expiresIn);
		} catch (UnsupportedOperationException e) {
			throw new ResponseStatusException(HttpStatus.SERVICE_UNAVAILABLE, e.getMessage(), e);
		}
		String token = jwtService.generateDirectUploadToken(owner, tenantId, safeName, target.storagePath());
		return new MediaDtos.DirectUploadInitResponse(target.uploadUrl(), target.storagePath(), token,
				target.expiresAt().toEpochMilli(), "PUT");
	}

	public MediaDtos.DirectUploadCompleteResponse completeDirectUpload(String owner,
			MediaDtos.DirectUploadCompleteRequest request) {
		return completeDirectUpload(owner, "legacy", request);
	}

	public MediaDtos.DirectUploadCompleteResponse completeDirectUpload(String owner, String tenantId,
			MediaDtos.DirectUploadCompleteRequest request) {
		Claims claims = parseDirectUploadToken(request.uploadToken());
		if (!owner.equals(claims.getSubject())) {
			throw new ResponseStatusException(HttpStatus.FORBIDDEN, "直传令牌不属于当前用户");
		}
		if (!tenantId.equals(claims.get("tenant_id", String.class))) {
			throw new ResponseStatusException(HttpStatus.FORBIDDEN, "直传令牌不属于当前工作区");
		}
		String fileName = claims.get("fileName", String.class);
		String storagePath = claims.get("storagePath", String.class);
		try {
			if (!mediaStorageService.objectExists(storagePath)) {
				throw new ResponseStatusException(HttpStatus.BAD_REQUEST, "对象存储尚未收到该视频文件");
			}
		} catch (IOException e) {
			throw new ResponseStatusException(HttpStatus.BAD_GATEWAY, "检查对象存储文件失败", e);
		}
		java.util.Optional<VideoTask> existing = videoTaskService.findLatestTaskByStoragePath(owner, storagePath);
		if (existing.isPresent()) {
			VideoTask task = existing.get();
			return new MediaDtos.DirectUploadCompleteResponse(task.getTaskId(), task.getVideoId(),
					task.getStoragePath(), task.getStatus().name());
		}
		VideoTask task = "legacy".equals(tenantId)
				? videoTaskService.createTask(owner, fileName, storagePath)
				: videoTaskService.createTaskInWorkspace(owner, tenantId, fileName, storagePath);
		return new MediaDtos.DirectUploadCompleteResponse(task.getTaskId(), task.getVideoId(),
				task.getStoragePath(), task.getStatus().name());
	}

	private Claims parseDirectUploadToken(String token) {
		try {
			Claims claims = jwtService.parse(token);
			if (!"direct-upload".equals(claims.get("purpose"))) {
				throw new ResponseStatusException(HttpStatus.FORBIDDEN, "直传令牌用途不匹配");
			}
			return claims;
		} catch (ResponseStatusException e) {
			throw e;
		} catch (Exception e) {
			throw new ResponseStatusException(HttpStatus.UNAUTHORIZED, "直传令牌无效或已过期");
		}
	}
}
