package com.example.videoplatform.media;

import com.example.videoplatform.config.AppProperties;
import com.example.videoplatform.workflow.VideoTask;
import com.example.videoplatform.workflow.VideoTaskService;
import com.example.videoplatform.workflow.WorkflowPublisher;
import java.io.IOException;
import java.io.InputStream;
import org.springframework.stereotype.Service;
import org.springframework.web.multipart.MultipartFile;

@Service
public class SingleUploadService {
	private static final org.slf4j.Logger log = org.slf4j.LoggerFactory.getLogger(SingleUploadService.class);

	private final AppProperties appProperties;
	private final VideoTaskService videoTaskService;
	private final WorkflowPublisher workflowPublisher;
	private final MediaStorageService mediaStorageService;

	public SingleUploadService(AppProperties appProperties,
			VideoTaskService videoTaskService,
			WorkflowPublisher workflowPublisher,
			MediaStorageService mediaStorageService) {
		this.appProperties = appProperties;
		this.videoTaskService = videoTaskService;
		this.workflowPublisher = workflowPublisher;
		this.mediaStorageService = mediaStorageService;
	}

	public MediaDtos.SingleUploadResponse uploadSingleFile(String owner, MultipartFile file) {
		return uploadSingleFile(owner, "legacy", file);
	}

	public MediaDtos.SingleUploadResponse uploadSingleFile(
			String owner, String tenantId, MultipartFile file) {
		MediaFileValidator.requireVideoFile(file);
		videoTaskService.assertCanCreateTask(owner);
		try {
			String safeName = MediaFileValidator.safeVideoFileName(file.getOriginalFilename());
			String stored;
			try (InputStream inputStream = file.getInputStream()) {
				stored = mediaStorageService.saveUpload(safeName, inputStream);
			}
			VideoTask task;
			try {
				task = "legacy".equals(tenantId)
						? videoTaskService.createTask(owner, safeName, stored)
						: videoTaskService.createTaskInWorkspace(owner, tenantId, safeName, stored);
			} catch (RuntimeException exception) {
				deleteRejectedUpload(stored);
				throw exception;
			}
			workflowPublisher.publish(task.getTaskId());
			return new MediaDtos.SingleUploadResponse(task.getTaskId(), task.getVideoId(), task.getStoragePath(),
					task.getStatus().name());
		} catch (IOException exception) {
			throw new IllegalArgumentException("保存上传文件失败", exception);
		}
	}

	private void deleteRejectedUpload(String storagePath) {
		try {
			mediaStorageService.delete(storagePath);
		} catch (IOException cleanupError) {
			log.warn("Failed to clean rejected upload {}", storagePath, cleanupError);
		}
	}
}
