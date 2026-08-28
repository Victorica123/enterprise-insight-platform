package com.example.videoplatform.media;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.never;
import static org.mockito.Mockito.when;

import com.example.videoplatform.auth.JwtService;
import com.example.videoplatform.config.AppProperties;
import com.example.videoplatform.workflow.VideoTask;
import com.example.videoplatform.workflow.VideoTaskService;
import com.example.videoplatform.workflow.WorkflowPublisher;
import java.time.Duration;
import java.time.Instant;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.web.server.ResponseStatusException;

class DirectUploadServiceTests {

	private final MediaStorageService mediaStorageService = org.mockito.Mockito.mock(MediaStorageService.class);
	private final VideoTaskService videoTaskService = org.mockito.Mockito.mock(VideoTaskService.class);
	private final WorkflowPublisher workflowPublisher = org.mockito.Mockito.mock(WorkflowPublisher.class);

	private DirectUploadService service;
	private JwtService jwtService;

	@BeforeEach
	void setUp() {
		AppProperties properties = new AppProperties();
		properties.getJwt().setSecret("01234567890123456789012345678901");
		properties.getJwt().setExpirationSeconds(3600);
		jwtService = new JwtService(properties);
		service = new DirectUploadService(mediaStorageService, jwtService, videoTaskService, workflowPublisher);
	}

	@Test
	void initDirectUploadReturnsBoundTokenAndStoragePath() {
		when(mediaStorageService.createDirectUploadTarget("demo.mp4", Duration.ofSeconds(900)))
				.thenReturn(new MediaStorageService.DirectUploadTarget("s3://video-platform/uploads/direct/demo.mp4",
						"http://localhost:19000/video-platform/uploads/direct/demo.mp4?signature=abc",
						Instant.parse("2026-07-03T00:00:00Z")));

		MediaDtos.DirectUploadInitResponse response = service.initDirectUpload("alice",
				new MediaDtos.DirectUploadInitRequest("demo.mp4", 1024L));

		assertThat(response.method()).isEqualTo("PUT");
		assertThat(response.storagePath()).isEqualTo("s3://video-platform/uploads/direct/demo.mp4");
		assertThat(response.uploadToken()).isNotBlank();
		verify(mediaStorageService).createDirectUploadTarget("demo.mp4", Duration.ofSeconds(900));
		verify(videoTaskService).assertCanCreateTask("alice");
	}

	@Test
	void initDirectUploadReportsServiceUnavailableWhenStorageDoesNotSupportIt() {
		when(mediaStorageService.createDirectUploadTarget("demo.mp4", Duration.ofSeconds(900)))
				.thenThrow(new UnsupportedOperationException("本地磁盘存储不支持浏览器直传，请切换 app.storage.type=s3"));

		assertThatThrownBy(() -> service.initDirectUpload("alice",
				new MediaDtos.DirectUploadInitRequest("demo.mp4", 1024L)))
				.isInstanceOf(ResponseStatusException.class)
				.hasMessageContaining("503 SERVICE_UNAVAILABLE");
	}

	@Test
	void completeDirectUploadCreatesTaskAfterObjectExists() throws Exception {
		String token = jwtService.generateDirectUploadToken("alice", "demo.mp4",
				"s3://video-platform/uploads/direct/demo.mp4");
		when(mediaStorageService.objectExists("s3://video-platform/uploads/direct/demo.mp4")).thenReturn(true);
		VideoTask task = new VideoTask("task-1", "video-1", "alice", "demo.mp4",
				"s3://video-platform/uploads/direct/demo.mp4");
		when(videoTaskService.createTask("alice", "demo.mp4", "s3://video-platform/uploads/direct/demo.mp4"))
				.thenReturn(task);

		MediaDtos.DirectUploadCompleteResponse response = service.completeDirectUpload("alice",
				new MediaDtos.DirectUploadCompleteRequest(token));

		assertThat(response.taskId()).isEqualTo("task-1");
		assertThat(response.status()).isEqualTo("QUEUED");
		verify(workflowPublisher).publish("task-1");
	}

	@Test
	void completeDirectUploadIsIdempotentForSameStoragePath() throws Exception {
		String token = jwtService.generateDirectUploadToken("alice", "demo.mp4",
				"s3://video-platform/uploads/direct/demo.mp4");
		when(mediaStorageService.objectExists("s3://video-platform/uploads/direct/demo.mp4")).thenReturn(true);
		VideoTask existing = new VideoTask("task-existing", "video-existing", "alice", "demo.mp4",
				"s3://video-platform/uploads/direct/demo.mp4");
		when(videoTaskService.findLatestTaskByStoragePath("alice", "s3://video-platform/uploads/direct/demo.mp4"))
				.thenReturn(java.util.Optional.of(existing));

		MediaDtos.DirectUploadCompleteResponse response = service.completeDirectUpload("alice",
				new MediaDtos.DirectUploadCompleteRequest(token));

		assertThat(response.taskId()).isEqualTo("task-existing");
		verify(videoTaskService, never()).createTask(org.mockito.Mockito.any(), org.mockito.Mockito.any(),
				org.mockito.Mockito.any());
		verify(workflowPublisher, never()).publish(org.mockito.Mockito.any());
	}

	@Test
	void completeDirectUploadRejectsDifferentOwnerToken() {
		String token = jwtService.generateDirectUploadToken("bob", "demo.mp4",
				"s3://video-platform/uploads/direct/demo.mp4");

		assertThatThrownBy(() -> service.completeDirectUpload("alice",
				new MediaDtos.DirectUploadCompleteRequest(token)))
				.isInstanceOf(ResponseStatusException.class)
				.hasMessageContaining("403 FORBIDDEN");
	}
}
