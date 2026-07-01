package com.example.videoplatform.media;

import com.example.videoplatform.config.AppProperties;
import com.example.videoplatform.workflow.VideoTask;
import com.example.videoplatform.workflow.VideoTaskService;
import com.example.videoplatform.workflow.WorkflowPublisher;
import java.io.IOException;
import java.io.InputStream;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.StandardCopyOption;
import java.util.UUID;
import org.springframework.stereotype.Service;
import org.springframework.web.multipart.MultipartFile;

@Service
public class SingleUploadService {

	private final AppProperties appProperties;
	private final VideoTaskService videoTaskService;
	private final WorkflowPublisher workflowPublisher;

	public SingleUploadService(AppProperties appProperties,
			VideoTaskService videoTaskService,
			WorkflowPublisher workflowPublisher) {
		this.appProperties = appProperties;
		this.videoTaskService = videoTaskService;
		this.workflowPublisher = workflowPublisher;
	}

	public MediaDtos.SingleUploadResponse uploadSingleFile(String owner, MultipartFile file) {
		MediaFileValidator.requireVideoFile(file);
		try {
			Path baseDir = Path.of(appProperties.getStorage().getBasePath()).resolve("uploads");
			Files.createDirectories(baseDir);
			String safeName = MediaFileValidator.safeVideoFileName(file.getOriginalFilename());
			Path stored = baseDir.resolve(UUID.randomUUID() + "-" + safeName);
			try (InputStream inputStream = file.getInputStream()) {
				Files.copy(inputStream, stored, StandardCopyOption.REPLACE_EXISTING);
			}
			VideoTask task = videoTaskService.createTask(owner, safeName, stored.toString());
			workflowPublisher.publish(task.getTaskId());
			return new MediaDtos.SingleUploadResponse(task.getTaskId(), task.getVideoId(), task.getStoragePath(),
					task.getStatus().name());
		} catch (IOException exception) {
			throw new IllegalArgumentException("保存上传文件失败", exception);
		}
	}
}
