package com.example.videoplatform.transcript;

import java.time.Instant;
import org.springframework.boot.autoconfigure.condition.ConditionalOnProperty;
import org.springframework.stereotype.Service;

@Service
@ConditionalOnProperty(prefix = "app.transcript", name = "enabled", havingValue = "false", matchIfMissing = true)
public class MockTranscriptService implements TranscriptService {

	@Override
	public String extract(String storagePath, String fileName) {
		return "模拟转写结果: 文件 " + fileName + " 已完成音频识别。"
				+ " 存储路径 " + storagePath + "。"
				+ " 处理时间 " + Instant.now() + "。";
	}
}
