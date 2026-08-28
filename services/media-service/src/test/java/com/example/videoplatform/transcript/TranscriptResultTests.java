package com.example.videoplatform.transcript;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;

import java.util.List;
import org.junit.jupiter.api.Test;

class TranscriptResultTests {

	@Test
	void roundTripsTimestampedSegmentsForPersistence() {
		TranscriptResult original = new TranscriptResult(
				"第一段 第二段",
				List.of(
						new TranscriptResult.Segment("segment-0", 0, 1200, 4800, "客户", "第一段"),
						new TranscriptResult.Segment("segment-1", 1, 5100, 8900, "产品", "第二段")),
				"zh-CN",
				10_000L);

		TranscriptResult restored = TranscriptResult.fromStored(
				original.text(), original.segmentsJson(), original.language(), original.durationMs());

		assertThat(restored).isEqualTo(original);
	}

	@Test
	void rejectsInvalidTimeline() {
		assertThatThrownBy(() -> new TranscriptResult(
				"bad",
				List.of(new TranscriptResult.Segment("segment-1", 1, 100, 200, null, "bad")),
				null,
				1000L))
				.isInstanceOf(IllegalArgumentException.class)
				.hasMessageContaining("contiguous");
	}
}
