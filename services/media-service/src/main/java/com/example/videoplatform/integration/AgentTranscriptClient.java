package com.example.videoplatform.integration;

import com.example.videoplatform.config.AppProperties;
import jakarta.annotation.PostConstruct;
import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.nio.charset.StandardCharsets;
import java.time.Duration;
import java.time.Clock;
import org.springframework.stereotype.Component;

@Component
public class AgentTranscriptClient {

	private final AppProperties appProperties;
	private final AgentDeliveryCircuit circuit;
	private final HttpClient httpClient = HttpClient.newBuilder()
			// Uvicorn's local server is HTTP/1.1; avoid an h2c upgrade request being rejected
			// before the transcript payload reaches the FastAPI route.
			.version(HttpClient.Version.HTTP_1_1)
			.connectTimeout(Duration.ofSeconds(3))
			.build();

	@org.springframework.beans.factory.annotation.Autowired
	public AgentTranscriptClient(AppProperties appProperties) {
		this(appProperties, Clock.systemUTC());
	}

	AgentTranscriptClient(AppProperties appProperties, Clock clock) {
		this.appProperties = appProperties;
		this.circuit = new AgentDeliveryCircuit(appProperties.getIntegration().getAgent(), clock);
	}

	@PostConstruct
	void validateConfiguration() {
		AppProperties.Integration.Agent config = appProperties.getIntegration().getAgent();
		if (config.isEnabled() && (config.getServiceToken() == null || config.getServiceToken().isBlank())) {
			throw new IllegalStateException("Agent integration requires MEDIA_INGEST_SERVICE_TOKEN");
		}
		if (config.getCircuitFailureThreshold() < 1 || config.getCircuitOpenMs() < 1
				|| config.getCircuitMaxOpenMs() < config.getCircuitOpenMs()
				|| config.getClaimLeaseDurationMs() <= 15_000) {
			throw new IllegalStateException("Agent circuit settings must be positive and delivery lease must exceed HTTP timeout (15000ms)");
		}
	}

	public boolean canAttempt() { return circuit.canAttempt(); }

	public void send(String payload) {
		send(payload, () -> { });
	}

	/** Invokes the observer only after acquiring a circuit permit, immediately before network I/O. */
	void send(String payload, Runnable onAttempt) {
		AgentDeliveryCircuit.Permit permit = circuit.acquire();
		try {
			onAttempt.run();
		} catch (RuntimeException exception) {
			circuit.succeeded(permit);
			throw exception;
		}
		try {
			AppProperties.Integration.Agent config = appProperties.getIntegration().getAgent();
			String baseUrl = config.getBaseUrl().replaceAll("/+$", "");
			HttpRequest request = HttpRequest.newBuilder()
				.uri(URI.create(baseUrl + "/internal/v1/media/transcripts"))
				.timeout(Duration.ofSeconds(15))
				.header("Authorization", "Bearer " + config.getServiceToken())
				.header("Content-Type", "application/json")
				.POST(HttpRequest.BodyPublishers.ofString(payload, StandardCharsets.UTF_8))
				.build();
			HttpResponse<Void> response = httpClient.send(request, HttpResponse.BodyHandlers.discarding());
			if (response.statusCode() / 100 == 2) {
				circuit.succeeded(permit);
				return;
			}
			String message = "Agent ingestion returned HTTP " + response.statusCode();
			if (response.statusCode() >= 400 && response.statusCode() < 500
					&& response.statusCode() != 408 && response.statusCode() != 429) {
				throw new PermanentDeliveryException(message);
			}
			throw new IllegalStateException(message);
		} catch (PermanentDeliveryException exception) {
			circuit.succeeded(permit);
			throw exception;
		} catch (InterruptedException exception) {
			circuit.failed(permit);
			Thread.currentThread().interrupt();
			throw new IllegalStateException("Agent ingestion was interrupted", exception);
		} catch (RuntimeException exception) {
			circuit.failed(permit);
			throw exception;
		} catch (Exception exception) {
			circuit.failed(permit);
			throw new IllegalStateException("Agent ingestion request failed", exception);
		}
	}

	public static class PermanentDeliveryException extends IllegalStateException {
		public PermanentDeliveryException(String message) {
			super(message);
		}
	}
}
