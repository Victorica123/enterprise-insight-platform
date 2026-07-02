package com.example.videoplatform.media;

import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.verifyNoInteractions;
import static org.mockito.Mockito.when;
import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors.user;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.multipart;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

import com.example.videoplatform.auth.JwtService;
import com.example.videoplatform.config.SecurityConfig;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.WebMvcTest;
import org.springframework.boot.test.mock.mockito.MockBean;
import org.springframework.context.annotation.Import;
import org.springframework.mock.web.MockMultipartFile;
import org.springframework.test.web.servlet.MockMvc;

@WebMvcTest(MediaController.class)
@Import(SecurityConfig.class)
class MediaControllerTests {

	@Autowired
	private MockMvc mockMvc;

	@MockBean
	private SingleUploadService singleUploadService;

	@MockBean
	private ChunkUploadService chunkUploadService;

	@MockBean
	private JwtService jwtService;

	@Test
	void rejectsAnonymousUploadRequest() throws Exception {
		MockMultipartFile file = new MockMultipartFile("file", "demo.mp4", "video/mp4", new byte[] {1});

		mockMvc.perform(multipart("/api/media/upload/file").file(file))
				.andExpect(status().isForbidden());

		verifyNoInteractions(singleUploadService, chunkUploadService);
	}

	@Test
	void uploadsSingleFileForAuthenticatedOwner() throws Exception {
		MockMultipartFile file = new MockMultipartFile("file", "demo.mp4", "video/mp4", new byte[] {1});
		when(singleUploadService.uploadSingleFile("alice", file))
				.thenReturn(new MediaDtos.SingleUploadResponse("task-1", "video-1", "storage/demo.mp4", "QUEUED"));

		mockMvc.perform(multipart("/api/media/upload/file")
						.file(file)
						.with(user("alice")))
				.andExpect(status().isOk())
				.andExpect(jsonPath("$.success").value(true))
				.andExpect(jsonPath("$.data.taskId").value("task-1"));

		verify(singleUploadService).uploadSingleFile("alice", file);
	}

	@Test
	void initializesChunkUploadForAuthenticatedOwner() throws Exception {
		when(chunkUploadService.initUpload(org.mockito.Mockito.eq("alice"), org.mockito.Mockito.any()))
				.thenReturn(new MediaDtos.InitUploadResponse("upload-1", "/api/media/upload/chunk", 2, 1000L,
						null, false, java.util.List.of()));

		mockMvc.perform(org.springframework.test.web.servlet.request.MockMvcRequestBuilders
						.post("/api/media/upload/init")
						.contentType(org.springframework.http.MediaType.APPLICATION_JSON)
						.content("""
								{"fileName":"demo.mp4","fileSize":2,"totalChunks":2,"chunkSize":1}
								""")
						.with(user("alice")))
				.andExpect(status().isOk())
				.andExpect(jsonPath("$.data.uploadId").value("upload-1"));

		verify(chunkUploadService).initUpload(org.mockito.Mockito.eq("alice"), org.mockito.Mockito.any());
	}
}
