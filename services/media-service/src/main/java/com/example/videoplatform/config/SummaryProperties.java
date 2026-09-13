package com.example.videoplatform.config;

import org.springframework.boot.context.properties.ConfigurationProperties;

@ConfigurationProperties(prefix = "app.summary")
public class SummaryProperties extends FeatureProperties {
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
