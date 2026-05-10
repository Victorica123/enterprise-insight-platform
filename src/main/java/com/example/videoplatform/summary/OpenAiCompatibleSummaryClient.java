package com.example.videoplatform.summary;

import com.example.videoplatform.config.AppProperties;
import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import java.io.IOException;
import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.nio.charset.StandardCharsets;
import java.util.Map;
import org.springframework.stereotype.Component;

@Component
public class OpenAiCompatibleSummaryClient {

	private final AppProperties appProperties;
	private final ObjectMapper objectMapper;
	private final HttpClient httpClient;

	public OpenAiCompatibleSummaryClient(AppProperties appProperties, ObjectMapper objectMapper) {
		this.appProperties = appProperties;
		this.objectMapper = objectMapper;
		this.httpClient = HttpClient.newHttpClient();
	}

	public String summarize(String transcript) {
		AppProperties.Summary.Llm llm = appProperties.getSummary().getLlm();
		String baseUrl = llm.getApiBaseUrl();
		String apiKey = llm.getApiKey();
		if (isBlank(baseUrl) || isBlank(apiKey)) {
			throw new IllegalStateException("LLM 配置缺失，请设置 app.summary.llm.api-base-url 和 api-key");
		}

		try {
			Map<String, Object> payload = Map.of(
					"model", llm.getModel(),
					"messages", new Object[] {
							Map.of("role", "system", "content", llm.getSystemPrompt()),
							Map.of("role", "user", "content", transcript)
					},
					"temperature", 0.2);

			String requestBody = objectMapper.writeValueAsString(payload);
			HttpRequest request = HttpRequest.newBuilder()
					.uri(URI.create(trimTrailingSlash(baseUrl) + "/chat/completions"))
					.header("Authorization", "Bearer " + apiKey)
					.header("Content-Type", "application/json")
					.POST(HttpRequest.BodyPublishers.ofString(requestBody, StandardCharsets.UTF_8))
					.build();

			HttpResponse<String> response = httpClient.send(request, HttpResponse.BodyHandlers.ofString(StandardCharsets.UTF_8));
			if (response.statusCode() / 100 != 2) {
				throw new IllegalStateException("LLM 请求失败，status=" + response.statusCode() + "，body=" + response.body());
			}

			JsonNode root = objectMapper.readTree(response.body());
			JsonNode contentNode = root.path("choices").path(0).path("message").path("content");
			String content = contentNode.asText();
			if (isBlank(content)) {
				throw new IllegalStateException("LLM 响应缺少 content 字段: " + response.body());
			}
			return content;
		} catch (IOException exception) {
			throw new IllegalStateException("LLM 响应解析失败", exception);
		} catch (InterruptedException exception) {
			Thread.currentThread().interrupt();
			throw new IllegalStateException("LLM 请求被中断", exception);
		}
	}

	private static String trimTrailingSlash(String value) {
		return value.endsWith("/") ? value.substring(0, value.length() - 1) : value;
	}

	private static boolean isBlank(String value) {
		return value == null || value.trim().isEmpty();
	}
}
