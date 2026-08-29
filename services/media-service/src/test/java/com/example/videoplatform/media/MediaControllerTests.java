package com.example.videoplatform.media;

import static org.mockito.Mockito.doThrow;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.verifyNoInteractions;
import static org.mockito.Mockito.when;
import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors.authentication;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.multipart;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

import com.example.videoplatform.auth.JwtService;
import com.example.videoplatform.auth.WorkspacePrincipal;
import com.example.videoplatform.config.SecurityConfig;
import java.util.List;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.WebMvcTest;
import org.springframework.boot.test.mock.mockito.MockBean;
import org.springframework.context.annotation.Import;
import org.springframework.mock.web.MockMultipartFile;
import org.springframework.security.authentication.UsernamePasswordAuthenticationToken;
import org.springframework.security.core.authority.SimpleGrantedAuthority;
import org.springframework.test.web.servlet.MockMvc;
import org.springframework.test.web.servlet.request.RequestPostProcessor;

@WebMvcTest(MediaController.class)
@Import(SecurityConfig.class)
class MediaControllerTests {

	@Autowired MockMvc mockMvc;
	@MockBean SingleUploadService singleUploadService;
	@MockBean ChunkUploadService chunkUploadService;
	@MockBean DirectUploadService directUploadService;
	@MockBean JwtService jwtService;
	@MockBean com.example.videoplatform.auth.TokenBlacklist tokenBlacklist;

	@Test
	void rejectsAnonymousUploadRequest() throws Exception {
		MockMultipartFile file = videoFile();
		mockMvc.perform(multipart("/api/media/upload/file").file(file)).andExpect(status().isForbidden());
		verifyNoInteractions(singleUploadService, chunkUploadService, directUploadService);
	}

	@Test
	void uploadsSingleFileForAuthenticatedOwner() throws Exception {
		MockMultipartFile file = videoFile();
		when(singleUploadService.uploadSingleFile("alice", "tenant-a", file))
				.thenReturn(new MediaDtos.SingleUploadResponse("task-1", "video-1", "storage/demo.mp4", "QUEUED"));

		mockMvc.perform(multipart("/api/media/upload/file").file(file).with(workspaceUser("alice", "admin")))
				.andExpect(status().isOk())
				.andExpect(jsonPath("$.success").value(true))
				.andExpect(jsonPath("$.data.taskId").value("task-1"));
		verify(singleUploadService).uploadSingleFile("alice", "tenant-a", file);
	}

	@Test
	void returnsTooManyRequestsWhenUserTaskQuotaIsFull() throws Exception {
		MockMultipartFile file = videoFile();
		doThrow(new com.example.videoplatform.workflow.ActiveTaskLimitExceededException(5, 5))
				.when(singleUploadService).uploadSingleFile("alice", "tenant-a", file);

		mockMvc.perform(multipart("/api/media/upload/file").file(file).with(workspaceUser("alice", "admin")))
				.andExpect(status().isTooManyRequests())
				.andExpect(jsonPath("$.success").value(false))
				.andExpect(jsonPath("$.message").value(org.hamcrest.Matchers.containsString("单用户最多 5 个")));
	}

	@Test
	void returnsServiceUnavailableWhenLocalAsyncQueueIsFull() throws Exception {
		MockMultipartFile file = videoFile();
		doThrow(new org.springframework.core.task.TaskRejectedException("executor queue full"))
				.when(singleUploadService).uploadSingleFile("alice", "tenant-a", file);

		mockMvc.perform(multipart("/api/media/upload/file").file(file).with(workspaceUser("alice", "admin")))
				.andExpect(status().isServiceUnavailable())
				.andExpect(jsonPath("$.message").value(org.hamcrest.Matchers.containsString("自动补偿")));
	}

	@Test
	void initializesChunkUploadForAuthenticatedOwner() throws Exception {
		when(chunkUploadService.initUpload(org.mockito.Mockito.eq("alice"), org.mockito.Mockito.eq("tenant-a"),
				org.mockito.Mockito.any()))
				.thenReturn(new MediaDtos.InitUploadResponse("upload-1", "/api/media/upload/chunk", 2, 1000L,
						null, false, java.util.List.of()));

		mockMvc.perform(org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post("/api/media/upload/init")
						.contentType(org.springframework.http.MediaType.APPLICATION_JSON)
						.content("{\"fileName\":\"demo.mp4\",\"fileSize\":2,\"totalChunks\":2,\"chunkSize\":1}")
						.with(workspaceUser("alice", "admin")))
				.andExpect(status().isOk())
				.andExpect(jsonPath("$.data.uploadId").value("upload-1"));
		verify(chunkUploadService).initUpload(org.mockito.Mockito.eq("alice"), org.mockito.Mockito.eq("tenant-a"),
				org.mockito.Mockito.any());
	}

	@Test
	void initializesDirectUploadForAuthenticatedOwner() throws Exception {
		when(directUploadService.initDirectUpload(org.mockito.Mockito.eq("alice"), org.mockito.Mockito.eq("tenant-a"),
				org.mockito.Mockito.any()))
				.thenReturn(new MediaDtos.DirectUploadInitResponse("http://localhost:19000/video-platform/demo.mp4",
						"s3://video-platform/uploads/direct/demo.mp4", "token-1", 123456789L, "PUT"));

		mockMvc.perform(org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post("/api/media/upload/direct/init")
						.contentType(org.springframework.http.MediaType.APPLICATION_JSON)
						.content("{\"fileName\":\"demo.mp4\",\"fileSize\":1024}")
						.with(workspaceUser("alice", "admin")))
				.andExpect(status().isOk())
				.andExpect(jsonPath("$.data.method").value("PUT"))
				.andExpect(jsonPath("$.data.uploadToken").value("token-1"));
		verify(directUploadService).initDirectUpload(org.mockito.Mockito.eq("alice"),
				org.mockito.Mockito.eq("tenant-a"), org.mockito.Mockito.any());
	}

	@Test
	void completesDirectUploadForAuthenticatedOwner() throws Exception {
		when(directUploadService.completeDirectUpload(org.mockito.Mockito.eq("alice"),
				org.mockito.Mockito.eq("tenant-a"), org.mockito.Mockito.any()))
				.thenReturn(new MediaDtos.DirectUploadCompleteResponse("task-1", "video-1",
						"s3://video-platform/uploads/direct/demo.mp4", "QUEUED"));

		mockMvc.perform(org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post("/api/media/upload/direct/complete")
						.contentType(org.springframework.http.MediaType.APPLICATION_JSON)
						.content("{\"uploadToken\":\"token-1\"}")
						.with(workspaceUser("alice", "admin")))
				.andExpect(status().isOk())
				.andExpect(jsonPath("$.data.taskId").value("task-1"));
		verify(directUploadService).completeDirectUpload(org.mockito.Mockito.eq("alice"),
				org.mockito.Mockito.eq("tenant-a"), org.mockito.Mockito.any());
	}

	@Test
	void rejectsViewerUploadRequest() throws Exception {
		mockMvc.perform(multipart("/api/media/upload/file").file(videoFile()).with(workspaceUser("alice", "viewer")))
				.andExpect(status().isForbidden());
		verifyNoInteractions(singleUploadService, chunkUploadService, directUploadService);
	}

	private static MockMultipartFile videoFile() {
		return new MockMultipartFile("file", "demo.mp4", "video/mp4", new byte[] {1});
	}

	private static RequestPostProcessor workspaceUser(String userId, String role) {
		WorkspacePrincipal principal = new WorkspacePrincipal(userId, userId, "tenant-a", role, "team");
		return authentication(new UsernamePasswordAuthenticationToken(
				principal, null, List.of(new SimpleGrantedAuthority("ROLE_" + role.toUpperCase()))));
	}
}
