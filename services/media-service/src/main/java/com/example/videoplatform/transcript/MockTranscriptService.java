package com.example.videoplatform.transcript;

import com.example.videoplatform.config.AppProperties;
import java.time.Instant;
import org.springframework.boot.autoconfigure.condition.ConditionalOnProperty;
import org.springframework.stereotype.Service;

@Service
@ConditionalOnProperty(prefix = "app.transcript", name = "enabled", havingValue = "false", matchIfMissing = true)
public class MockTranscriptService implements TranscriptService {

	private final long mockDelayMs;

	public MockTranscriptService(AppProperties appProperties) {
		this.mockDelayMs = appProperties.getTranscript().getMockDelayMs();
	}

	@Override
	public TranscriptResult extract(String storagePath, String fileName) {
		simulateProcessingDelay();
		String text = "模拟转写结果: 文件 " + fileName + " 已完成音频识别。"
				+ " 存储路径 " + storagePath + "。"
				+ " 处理时间 " + Instant.now() + "。";
		return new TranscriptResult(
				text,
				java.util.List.of(new TranscriptResult.Segment("segment-0", 0, 0, 5_000, "演示说话人", text)),
				"zh-CN",
				5_000L);
	}

	/** 压测用：模拟真实转写的处理耗时（app.transcript.mock-delay-ms，默认 0 不生效）。 */
	private void simulateProcessingDelay() {
		if (mockDelayMs <= 0) {
			return;
		}
		try {
			Thread.sleep(mockDelayMs);
		} catch (InterruptedException interrupted) {
			Thread.currentThread().interrupt();
		}
	}
}
