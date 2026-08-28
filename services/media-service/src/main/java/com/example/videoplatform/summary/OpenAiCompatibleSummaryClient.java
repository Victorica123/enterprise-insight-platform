package com.example.videoplatform.summary;

import com.example.videoplatform.common.StringUtils;
import com.example.videoplatform.config.AppProperties;
import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import java.io.IOException;
import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.nio.charset.StandardCharsets;
import java.time.Duration;
import java.util.Map;
import org.springframework.stereotype.Component;

@Component
public class OpenAiCompatibleSummaryClient {

	private static final Duration CONNECT_TIMEOUT = Duration.ofSeconds(10);
	private static final Duration REQUEST_TIMEOUT = Duration.ofSeconds(60);

	private final AppProperties appProperties;
	private final ObjectMapper objectMapper;
	private final HttpClient httpClient;

	public OpenAiCompatibleSummaryClient(AppProperties appProperties, ObjectMapper objectMapper) {
		this.appProperties = appProperties;
		this.objectMapper = objectMapper;
		this.httpClient = HttpClient.newBuilder().connectTimeout(CONNECT_TIMEOUT).build();
	}

	public String summarize(String transcript) {
		if (StringUtils.isBlank(transcript)) {
			return "（该视频未检测到语音内容，无法生成总结）";
		}
		AppProperties.Summary.Llm llm = appProperties.getSummary().getLlm();
		String baseUrl = llm.getApiBaseUrl();
		String apiKey = llm.getApiKey();
		if (StringUtils.isBlank(baseUrl) || StringUtils.isBlank(apiKey)) {
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
					.uri(URI.create(StringUtils.trimTrailingSlash(baseUrl) + "/chat/completions"))
					.timeout(REQUEST_TIMEOUT)
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
			if (StringUtils.isBlank(content)) {
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
}
