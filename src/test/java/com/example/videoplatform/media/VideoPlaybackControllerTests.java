package com.example.videoplatform.media;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;
import static org.mockito.Mockito.mock;
import static org.mockito.Mockito.when;

import com.example.videoplatform.auth.JwtService;
import com.example.videoplatform.config.AppProperties;
import com.example.videoplatform.workflow.VideoTask;
import com.example.videoplatform.workflow.VideoTaskService;
import java.nio.file.Files;
import java.nio.file.Path;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.io.TempDir;
import org.springframework.http.HttpHeaders;
import org.springframework.mock.web.MockHttpServletResponse;
import org.springframework.security.authentication.UsernamePasswordAuthenticationToken;
import org.springframework.security.core.Authentication;
import org.springframework.web.server.ResponseStatusException;

class VideoPlaybackControllerTests {

	@TempDir
	Path storageRoot;

	private final VideoTaskService videoTaskService = mock(VideoTaskService.class);
	private JwtService jwtService;
	private VideoPlaybackController controller;

	@BeforeEach
	void setUp() {
		AppProperties props = new AppProperties();
		props.getJwt().setSecret("01234567890123456789012345678901");
		props.getJwt().setExpirationSeconds(3600);
		jwtService = new JwtService(props);
		controller = new VideoPlaybackController(videoTaskService, jwtService);
	}

	@Test
	void playbackTokenReturnsSignedStreamUrl() {
		VideoTask task = new VideoTask("task-1", "video-1", "alice", "demo.mp4", "/tmp/demo.mp4");
		when(videoTaskService.requireTask("task-1", "alice")).thenReturn(task);
		Authentication auth = new UsernamePasswordAuthenticationToken("alice", null);

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
}
