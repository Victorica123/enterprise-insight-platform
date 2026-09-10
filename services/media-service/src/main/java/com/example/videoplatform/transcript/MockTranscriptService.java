package com.example.videoplatform.transcript;

import com.example.videoplatform.config.AppProperties;
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
		// storagePath is an internal deployment detail. Even mock evidence enters
		// the cross-service transcript event and must never disclose it to users.
		String text = "模拟转写结果: 文件 " + fileName + " 已完成音频识别。"
				+ " 该内容仅用于验证处理与证据链路。";
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
