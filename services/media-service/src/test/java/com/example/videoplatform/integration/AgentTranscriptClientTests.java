package com.example.videoplatform.integration;

import static org.assertj.core.api.Assertions.assertThatThrownBy;
import static org.assertj.core.api.Assertions.assertThat;

import com.example.videoplatform.config.AppProperties;
import com.sun.net.httpserver.HttpServer;
import java.net.InetSocketAddress;
import org.junit.jupiter.api.AfterEach;
import org.junit.jupiter.api.Test;

class AgentTranscriptClientTests {

	private HttpServer server;

	@Test
	void repeatedServiceFailuresStopNetworkCallsUntilTheProbeSucceeds() throws Exception {
		var calls = new java.util.concurrent.atomic.AtomicInteger();
		var responseCode = new java.util.concurrent.atomic.AtomicInteger(503);
		server = HttpServer.create(new InetSocketAddress("127.0.0.1", 0), 0);
		server.createContext("/internal/v1/media/transcripts", exchange -> {
			calls.incrementAndGet();
			exchange.sendResponseHeaders(responseCode.get(), 0);
			exchange.close();
		});
		server.start();
		AppProperties properties = new AppProperties();
		properties.getIntegration().getAgent().setBaseUrl("http://127.0.0.1:" + server.getAddress().getPort());
		properties.getIntegration().getAgent().setServiceToken("test-service-token");
		var clock = new AgentDeliveryCircuitTests.MutableClock();
		var client = new AgentTranscriptClient(properties, clock);
		for (int i = 0; i < 3; i++) assertThatThrownBy(() -> client.send("{}")).hasMessageContaining("503");
		assertThatThrownBy(() -> client.send("{}")).isInstanceOf(AgentDeliveryCircuit.OpenException.class);
		assertThat(calls.get()).isEqualTo(3);
		clock.advance(30_000);
		responseCode.set(204);
		client.send("{}");
		assertThat(calls.get()).isEqualTo(4);
		assertThat(client.canAttempt()).isTrue();
	}

	@AfterEach
	void stopServer() {
		if (server != null) server.stop(0);
	}

	@Test
	void classifiesInvalidContractAsPermanentAndServiceFailureAsRetryable() throws Exception {
		server = HttpServer.create(new InetSocketAddress("127.0.0.1", 0), 0);
		server.createContext("/invalid/internal/v1/media/transcripts", exchange -> {
			exchange.sendResponseHeaders(422, 0);
			exchange.close();
		});
		server.createContext("/unavailable/internal/v1/media/transcripts", exchange -> {
			exchange.sendResponseHeaders(503, 0);
			exchange.close();
		});
		server.start();

		assertThatThrownBy(() -> client("/invalid").send("{}"))
				.isInstanceOf(AgentTranscriptClient.PermanentDeliveryException.class)
				.hasMessageContaining("422");
		assertThatThrownBy(() -> client("/unavailable").send("{}"))
				.isInstanceOf(IllegalStateException.class)
				.isNotInstanceOf(AgentTranscriptClient.PermanentDeliveryException.class)
				.hasMessageContaining("503");
	}

	private AgentTranscriptClient client(String prefix) {
		AppProperties properties = new AppProperties();
		properties.getIntegration().getAgent().setBaseUrl(
				"http://127.0.0.1:" + server.getAddress().getPort() + prefix);
		properties.getIntegration().getAgent().setServiceToken("test-service-token");
		return new AgentTranscriptClient(properties);
	}
}
