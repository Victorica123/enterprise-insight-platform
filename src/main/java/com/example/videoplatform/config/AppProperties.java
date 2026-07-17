package com.example.videoplatform.config;

import java.time.Duration;
import org.springframework.boot.context.properties.ConfigurationProperties;

@ConfigurationProperties(prefix = "app")
public class AppProperties {

	private final Jwt jwt = new Jwt();
	private final Storage storage = new Storage();
	private final Workflow workflow = new Workflow();
	private final Transcript transcript = new Transcript();
	private final Summary summary = new Summary();

	public Jwt getJwt() {
		return jwt;
	}

	public Storage getStorage() {
		return storage;
	}

	public Workflow getWorkflow() {
		return workflow;
	}

	public Transcript getTranscript() {
		return transcript;
	}

	public Summary getSummary() {
		return summary;
	}

	public static class Jwt {
		private String secret;
		private long expirationSeconds;

		public String getSecret() {
			return secret;
		}

		public void setSecret(String secret) {
			this.secret = secret;
		}

		public long getExpirationSeconds() {
			return expirationSeconds;
		}

		public void setExpirationSeconds(long expirationSeconds) {
			this.expirationSeconds = expirationSeconds;
		}
	}

	public static class Storage {
		private String basePath;
		private String type = "local";
		private final S3 s3 = new S3();

		public String getBasePath() {
			return basePath;
		}

		public void setBasePath(String basePath) {
			this.basePath = basePath;
		}

		public String getType() {
			return type;
		}

		public void setType(String type) {
			this.type = type;
		}

		public S3 getS3() {
			return s3;
		}

		public static class S3 {
			private String endpoint;
			private String publicEndpoint;
			private String region = "us-east-1";
			private String bucket = "video-platform";
			private String accessKey;
			private String secretKey;
			private boolean pathStyleAccess = true;

			public String getEndpoint() {
				return endpoint;
			}

			public void setEndpoint(String endpoint) {
				this.endpoint = endpoint;
			}

			public String getPublicEndpoint() {
				return publicEndpoint;
			}

			public void setPublicEndpoint(String publicEndpoint) {
				this.publicEndpoint = publicEndpoint;
			}

			public String getRegion() {
				return region;
			}

			public void setRegion(String region) {
				this.region = region;
			}

			public String getBucket() {
				return bucket;
			}

			public void setBucket(String bucket) {
				this.bucket = bucket;
			}

			public String getAccessKey() {
				return accessKey;
			}

			public void setAccessKey(String accessKey) {
				this.accessKey = accessKey;
			}

			public String getSecretKey() {
				return secretKey;
			}

			public void setSecretKey(String secretKey) {
				this.secretKey = secretKey;
			}

			public boolean isPathStyleAccess() {
				return pathStyleAccess;
			}

			public void setPathStyleAccess(boolean pathStyleAccess) {
				this.pathStyleAccess = pathStyleAccess;
			}
		}
	}

	public static class Workflow {
		private Duration staleTaskTimeout = Duration.ofHours(1);

		public Duration getStaleTaskTimeout() {
			return staleTaskTimeout;
		}

		public void setStaleTaskTimeout(Duration staleTaskTimeout) {
			this.staleTaskTimeout = staleTaskTimeout;
		}
	}

	public static class Feature {
		private boolean enabled;

		public boolean isEnabled() {
			return enabled;
		}

		public void setEnabled(boolean enabled) {
			this.enabled = enabled;
		}
	}

	public static class Transcript extends Feature {
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

	public static class Summary extends Feature {
		private final Llm llm = new Llm();

		public Llm getLlm() {
			return llm;
		}

		public static class Llm {
			private String apiBaseUrl;
			private String apiKey;
			private String model = "gpt-4o-mini";
			private String systemPrompt = "请将以下视频转写内容总结为3-5条要点，并给出一个简短结论。";

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

			public String getSystemPrompt() {
				return systemPrompt;
			}

			public void setSystemPrompt(String systemPrompt) {
				this.systemPrompt = systemPrompt;
			}
		}
	}
}
