package com.example.videoplatform.transcript;

import static org.assertj.core.api.Assertions.assertThat;

import com.example.videoplatform.config.AppProperties;
import org.junit.jupiter.api.Test;

class MockTranscriptServiceTests {

	@Test
	void returnsImmediatelyWhenDelayNotConfigured() {
		MockTranscriptService service = new MockTranscriptService(new AppProperties());

		long start = System.nanoTime();
		String transcript = service.extract("storage/demo.mp4", "demo.mp4");
		long elapsedMs = (System.nanoTime() - start) / 1_000_000;

		assertThat(transcript).contains("demo.mp4").contains("storage/demo.mp4");
		// 默认 mock-delay-ms=0：不引入任何等待（给足余量防抖动）
		assertThat(elapsedMs).isLessThan(500);
	}

	@Test
	void appliesConfiguredMockDelayForLoadTests() {
		AppProperties properties = new AppProperties();
		properties.getTranscript().setMockDelayMs(80);
		MockTranscriptService service = new MockTranscriptService(properties);

		long start = System.nanoTime();
		service.extract("storage/demo.mp4", "demo.mp4");
		long elapsedMs = (System.nanoTime() - start) / 1_000_000;

		// 压测旋钮生效：extract 至少耗时 mock-delay-ms
		assertThat(elapsedMs).isGreaterThanOrEqualTo(80);
	}
}
