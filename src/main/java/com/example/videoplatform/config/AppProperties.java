package com.example.videoplatform.config;

import org.springframework.boot.context.properties.ConfigurationProperties;

@ConfigurationProperties(prefix = "app")
public class AppProperties {

	private final Jwt jwt = new Jwt();
	private final Storage storage = new Storage();
	private final Transcript transcript = new Transcript();
	private final Summary summary = new Summary();

	public Jwt getJwt() {
		return jwt;
	}

	public Storage getStorage() {
		return storage;
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

		public String getBasePath() {
			return basePath;
		}

		public void setBasePath(String basePath) {
			this.basePath = basePath;
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
		private final Whisper whisper = new Whisper();

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
