package com.example.videoplatform.crawl;

import static org.assertj.core.api.Assertions.assertThatThrownBy;
import static org.mockito.Mockito.verifyNoInteractions;

import org.junit.jupiter.api.Test;

class CrawledVideoServiceTests {

	private final CrawledVideoRepository repository = org.mockito.Mockito.mock(CrawledVideoRepository.class);
	private final CrawledVideoService service = new CrawledVideoService(repository);

	@Test
	void rejectsBlankSiteBeforeRepositoryAccess() {
		CrawlDtos.UpsertCrawledVideoRequest request = new CrawlDtos.UpsertCrawledVideoRequest(
				" ",
				"source-1",
				"title",
				null,
				null,
				null,
				null,
				null,
				null,
				null,
				null,
				null,
				null,
				null,
				null,
				null,
				null,
				null,
				null);

		assertThatThrownBy(() -> service.upsert("user-1", request))
				.isInstanceOf(IllegalArgumentException.class)
				.hasMessageContaining("site");
		verifyNoInteractions(repository);
	}
}
