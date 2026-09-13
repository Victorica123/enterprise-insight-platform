package com.example.videoplatform.config;

import org.springframework.boot.context.properties.ConfigurationProperties;

@ConfigurationProperties(prefix = "app.transcript")
public class TranscriptProperties extends FeatureProperties {
	/**
	 * Mock 转写的模拟处理耗时（毫秒），默认 0（即刻返回，不影响正常使用）。
	 * 压测（P2 MQ 量化验证）时设为秒级，还原真实转写的慢消费者特征——否则
	 * Mock 即刻返回，线程池永不饱和，本地 @Async 与 MQ 削峰的差异无法测出。
	 */
	private long mockDelayMs;

	private final Whisper whisper = new Whisper();

	public long getMockDelayMs() {
		return mockDelayMs;
	}

	public void setMockDelayMs(long mockDelayMs) {
		this.mockDelayMs = mockDelayMs;
	}

	public Whisper getWhisper() {
		return whisper;
	}

	public static class Whisper {
		private String apiBaseUrl;
		private String apiKey;
		private String model = "whisper-1";
		private String ffmpegPath = "ffmpeg";

		public String getApiBaseUrl() {
			return apiBaseUrl;
		}

		public void setApiBaseUrl(String apiBaseUrl) {
			this.apiBaseUrl = apiBaseUrl;
		}

		public String getApiKey() {
			return apiKey;
		}

		public void setApiKey(String apiKey) {
			this.apiKey = apiKey;
		}

		public String getModel() {
			return model;
		}

		public void setModel(String model) {
			this.model = model;
		}

		public String getFfmpegPath() {
			return ffmpegPath;
		}

		public void setFfmpegPath(String ffmpegPath) {
			this.ffmpegPath = ffmpegPath;
		}
	}
}
