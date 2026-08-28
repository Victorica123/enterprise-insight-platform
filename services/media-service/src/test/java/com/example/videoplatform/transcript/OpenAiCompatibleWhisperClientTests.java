package com.example.videoplatform.transcript;

import static org.assertj.core.api.Assertions.assertThat;

import com.example.videoplatform.config.AppProperties;
import com.fasterxml.jackson.databind.ObjectMapper;
import org.junit.jupiter.api.Test;

class OpenAiCompatibleWhisperClientTests {

	private final OpenAiCompatibleWhisperClient client =
			new OpenAiCompatibleWhisperClient(new AppProperties(), new ObjectMapper());

	@Test
	void parsesVerboseSegmentsIntoMilliseconds() {
		TranscriptResult result = client.parseTranscript("""
				{
				  "text": "预算审批必须三日内完成。",
				  "language": "zh",
				  "duration": 6.5,
				  "segments": [
				    {"id": 3, "start": 1.2, "end": 4.8, "text": "预算审批必须三日内完成。", "speaker": "客户"}
				  ]
				}
				""");

		assertThat(result.language()).isEqualTo("zh");
		assertThat(result.durationMs()).isEqualTo(6500);
		assertThat(result.segments()).singleElement().satisfies(segment -> {
			assertThat(segment.segmentId()).isEqualTo("segment-3");
			assertThat(segment.startMs()).isEqualTo(1200);
			assertThat(segment.endMs()).isEqualTo(4800);
			assertThat(segment.speaker()).isEqualTo("客户");
		});
	}

	@Test
	void degradesPlainJsonToAddressableFallbackSegment() {
		TranscriptResult result = client.parseTranscript("{\"text\":\"只有文本\"}");

		assertThat(result.segments()).singleElement().satisfies(segment -> {
			assertThat(segment.segmentId()).isEqualTo("segment-0");
			assertThat(segment.startMs()).isZero();
			assertThat(segment.endMs()).isZero();
		});
	}
}
