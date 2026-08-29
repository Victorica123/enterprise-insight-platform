package com.example.videoplatform.integration;

import com.example.videoplatform.config.AppProperties;
import jakarta.annotation.PostConstruct;
import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.nio.charset.StandardCharsets;
import java.time.Duration;
import org.springframework.stereotype.Component;

@Component
public class AgentTranscriptClient {

	private final AppProperties appProperties;
	private final HttpClient httpClient = HttpClient.newBuilder()
			// Uvicorn's local server is HTTP/1.1; avoid an h2c upgrade request being rejected
			// before the transcript payload reaches the FastAPI route.
			.version(HttpClient.Version.HTTP_1_1)
			.connectTimeout(Duration.ofSeconds(3))
			.build();

	public AgentTranscriptClient(AppProperties appProperties) {
		this.appProperties = appProperties;
	}

	@PostConstruct
	void validateConfiguration() {
		AppProperties.Integration.Agent config = appProperties.getIntegration().getAgent();
		if (config.isEnabled() && (config.getServiceToken() == null || config.getServiceToken().isBlank())) {
			throw new IllegalStateException("Agent integration requires MEDIA_INGEST_SERVICE_TOKEN");
		}
	}

	public void send(String payload) {
		AppProperties.Integration.Agent config = appProperties.getIntegration().getAgent();
		String baseUrl = config.getBaseUrl().replaceAll("/+$", "");
		HttpRequest request = HttpRequest.newBuilder()
				.uri(URI.create(baseUrl + "/internal/v1/media/transcripts"))
				.timeout(Duration.ofSeconds(15))
				.header("Authorization", "Bearer " + config.getServiceToken())
				.header("Content-Type", "application/json")
				.POST(HttpRequest.BodyPublishers.ofString(payload, StandardCharsets.UTF_8))
				.build();
		try {
			HttpResponse<String> response = httpClient.send(
					request, HttpResponse.BodyHandlers.ofString(StandardCharsets.UTF_8));
			if (response.statusCode() / 100 == 2) {
				return;
			}
			String message = "Agent ingestion returned " + response.statusCode() + ": " + response.body();
			if (response.statusCode() >= 400 && response.statusCode() < 500
					&& response.statusCode() != 408 && response.statusCode() != 429) {
				throw new PermanentDeliveryException(message);
			}
			throw new IllegalStateException(message);
		} catch (PermanentDeliveryException exception) {
			throw exception;
		} catch (InterruptedException exception) {
			Thread.currentThread().interrupt();
			throw new IllegalStateException("Agent ingestion was interrupted", exception);
		} catch (RuntimeException exception) {
			throw exception;
		} catch (Exception exception) {
			throw new IllegalStateException("Agent ingestion request failed", exception);
		}
	}

	public static class PermanentDeliveryException extends IllegalStateException {
		public PermanentDeliveryException(String message) {
			super(message);
		}
	}
}
