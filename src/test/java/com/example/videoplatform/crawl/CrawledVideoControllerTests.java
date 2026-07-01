package com.example.videoplatform.crawl;

import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.verifyNoInteractions;
import static org.mockito.Mockito.when;
import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors.user;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

import com.example.videoplatform.auth.JwtService;
import com.example.videoplatform.config.SecurityConfig;
import java.util.List;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.WebMvcTest;
import org.springframework.boot.test.mock.mockito.MockBean;
import org.springframework.context.annotation.Import;
import org.springframework.data.domain.PageImpl;
import org.springframework.data.domain.PageRequest;
import org.springframework.test.web.servlet.MockMvc;

@WebMvcTest(CrawledVideoController.class)
@Import(SecurityConfig.class)
class CrawledVideoControllerTests {

	@Autowired
	private MockMvc mockMvc;

	@MockBean
	private CrawledVideoService service;

	@MockBean
	private JwtService jwtService;

	@Test
	void rejectsAnonymousListRequest() throws Exception {
		mockMvc.perform(get("/api/crawled-videos"))
				.andExpect(status().isForbidden());

		verifyNoInteractions(service);
	}

	@Test
	void listsOnlyAuthenticatedUsersCrawledVideos() throws Exception {
		CrawlDtos.UpsertCrawledVideoRequest request = new CrawlDtos.UpsertCrawledVideoRequest(
				"bilibili", "source-1", "title", null, null, null, null, null, null, null,
				null, null, null, null, null, null, null, null, null);
		CrawledVideo video = new CrawledVideo("alice", request);
		when(service.list("alice", "bilibili", 0, 20))
				.thenReturn(new PageImpl<>(List.of(video), PageRequest.of(0, 20), 1));

		mockMvc.perform(get("/api/crawled-videos")
						.param("site", "bilibili")
						.with(user("alice")))
				.andExpect(status().isOk())
				.andExpect(jsonPath("$.success").value(true))
				.andExpect(jsonPath("$.data.content[0].owner").value("alice"));

		verify(service).list("alice", "bilibili", 0, 20);
	}

	@Test
	void loadsCrawledVideoByAuthenticatedOwner() throws Exception {
		CrawlDtos.UpsertCrawledVideoRequest request = new CrawlDtos.UpsertCrawledVideoRequest(
				"bilibili", "source-1", "title", null, null, null, null, null, null, null,
				null, null, null, null, null, null, null, null, null);
		CrawledVideo video = new CrawledVideo("alice", request);
		when(service.require("alice", "video-1")).thenReturn(video);

		mockMvc.perform(get("/api/crawled-videos/video-1").with(user("alice")))
				.andExpect(status().isOk())
				.andExpect(jsonPath("$.data.owner").value("alice"));

		verify(service).require("alice", "video-1");
	}
}
