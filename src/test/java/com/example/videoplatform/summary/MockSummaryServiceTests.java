package com.example.videoplatform.summary;

import static org.assertj.core.api.Assertions.assertThat;

import org.junit.jupiter.api.Test;

class MockSummaryServiceTests {

	private final MockSummaryService summaryService = new MockSummaryService();

	@Test
	void returnsFriendlyMessageForBlankTranscript() {
		assertThat(summaryService.summarize(" "))
				.contains("no speech content");
	}

	@Test
	void truncatesLongTranscriptPreview() {
		String summary = summaryService.summarize("a".repeat(120));

		assertThat(summary).contains("a".repeat(100) + "...");
	}
}
