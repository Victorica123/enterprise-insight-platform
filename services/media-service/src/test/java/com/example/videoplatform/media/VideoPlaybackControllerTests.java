package com.example.videoplatform.media;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;
import static org.mockito.Mockito.mock;
import static org.mockito.Mockito.when;

import com.example.videoplatform.auth.JwtService;
import com.example.videoplatform.auth.WorkspacePrincipal;
import com.example.videoplatform.config.AppProperties;
import com.example.videoplatform.workflow.VideoTask;
import com.example.videoplatform.workflow.VideoTaskService;
import java.nio.file.Files;
import java.nio.file.Path;
import java.time.Duration;
import java.util.List;
import java.util.Optional;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.io.TempDir;
import org.springframework.http.HttpHeaders;
import org.springframework.mock.web.MockHttpServletResponse;
import org.springframework.security.authentication.UsernamePasswordAuthenticationToken;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.authority.SimpleGrantedAuthority;
import org.springframework.web.server.ResponseStatusException;

class VideoPlaybackControllerTests {

	@TempDir
	Path storageRoot;

	private final VideoTaskService videoTaskService = mock(VideoTaskService.class);
	private final MediaStorageService mediaStorageService = mock(MediaStorageService.class);
	private JwtService jwtService;
	private VideoPlaybackController controller;

	@BeforeEach
	void setUp() {
		AppProperties props = new AppProperties();
		props.getJwt().setSecret("01234567890123456789012345678901");
		props.getJwt().setExpirationSeconds(3600);
		props.getStorage().setBasePath(storageRoot.toString());
		jwtService = new JwtService(props);
		when(mediaStorageService.createPlaybackRedirectUrl(org.mockito.Mockito.anyString(), org.mockito.Mockito.any()))
				.thenReturn(Optional.empty());
		when(mediaStorageService.requireLocalPath(org.mockito.Mockito.anyString()))
				.thenAnswer(invocation -> Path.of(invocation.getArgument(0, String.class)));
		controller = new VideoPlaybackController(videoTaskService, jwtService, mediaStorageService);
	}

	@Test
	void playbackTokenReturnsSignedStreamUrl() {
		VideoTask task = new VideoTask("task-1", "video-1", "alice", "demo.mp4", "/tmp/demo.mp4");
		when(videoTaskService.requireTaskForWorkspace("task-1", "tenant-a", "alice", true)).thenReturn(task);
		Authentication auth = new UsernamePasswordAuthenticationToken(
				new WorkspacePrincipal("alice", "alice", "tenant-a", "operator", "team"), null,
				List.of(new SimpleGrantedAuthority("ROLE_OPERATOR")));

		MediaDtos.PlaybackTokenResponse response = controller.playbackToken(auth, "task-1").data();

		assertThat(response.token()).isNotBlank();
		assertThat(response.streamUrl()).contains("/api/media/video/task-1/stream?token=");
		assertThat(response.expiresInSeconds()).isEqualTo(3600L);
	}

	@Test
	void streamServesRangeRequestAsPartialContent() throws Exception {
		Path video = storageRoot.resolve("video.mp4");
		byte[] content = new byte[100];
		for (int i = 0; i < content.length; i++) {
			content[i] = (byte) i;
		}
		Files.write(video, content);
		VideoTask task = new VideoTask("task-1", "video-1", "alice", "video.mp4", video.toString());
		when(videoTaskService.requireTask("task-1", "alice")).thenReturn(task);
		String token = jwtService.generatePlaybackToken("task-1", "alice");
		MockHttpServletResponse response = new MockHttpServletResponse();

		controller.stream("task-1", token, "bytes=0-9", response);

		assertThat(response.getStatus()).isEqualTo(206);
		assertThat(response.getHeader(HttpHeaders.CONTENT_RANGE)).isEqualTo("bytes 0-9/100");
		assertThat(response.getHeader(HttpHeaders.ACCEPT_RANGES)).isEqualTo("bytes");
		assertThat(response.getContentAsByteArray()).hasSize(10);
	}

	@Test
	void streamServesFullFileWhenNoRangeHeader() throws Exception {
		Path video = storageRoot.resolve("video.mp4");
		Files.write(video, new byte[] {1, 2, 3, 4, 5});
		VideoTask task = new VideoTask("task-1", "video-1", "alice", "video.mp4", video.toString());
		when(videoTaskService.requireTask("task-1", "alice")).thenReturn(task);
		String token = jwtService.generatePlaybackToken("task-1", "alice");
		MockHttpServletResponse response = new MockHttpServletResponse();

		controller.stream("task-1", token, null, response);

		assertThat(response.getStatus()).isEqualTo(200);
		assertThat(response.getContentAsByteArray()).hasSize(5);
	}

	@Test
	void streamRejectsTamperedToken() {
		MockHttpServletResponse response = new MockHttpServletResponse();

		assertThatThrownBy(() -> controller.stream("task-1", "not.a.valid.token", null, response))
				.isInstanceOf(ResponseStatusException.class);
	}

	@Test
	void streamRejectsTokenIssuedForDifferentTask() {
		String token = jwtService.generatePlaybackToken("task-OTHER", "alice");
		MockHttpServletResponse response = new MockHttpServletResponse();

		assertThatThrownBy(() -> controller.stream("task-1", token, null, response))
				.isInstanceOf(ResponseStatusException.class);
	}

	@Test
	void streamRedirectsToObjectStoragePresignedUrlWhenAvailable() throws Exception {
		VideoTask task = new VideoTask("task-1", "video-1", "alice", "video.mp4",
				"s3://video-platform/uploads/video.mp4");
		when(videoTaskService.requireTask("task-1", "alice")).thenReturn(task);
		when(mediaStorageService.createPlaybackRedirectUrl(org.mockito.Mockito.eq(task.getStoragePath()),
				org.mockito.Mockito.any(Duration.class)))
				.thenReturn(Optional.of("http://localhost:9000/video-platform/uploads/video.mp4?X-Amz-Signature=abc"));
		String token = jwtService.generatePlaybackToken("task-1", "alice");
		MockHttpServletResponse response = new MockHttpServletResponse();

		controller.stream("task-1", token, null, response);

		assertThat(response.getStatus()).isEqualTo(307);
		assertThat(response.getHeader(HttpHeaders.LOCATION))
				.contains("X-Amz-Signature=abc");
	}
}
