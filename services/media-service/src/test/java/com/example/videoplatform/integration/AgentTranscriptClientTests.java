package com.example.videoplatform.integration;

import static org.assertj.core.api.Assertions.assertThatThrownBy;

import com.example.videoplatform.config.AppProperties;
import com.sun.net.httpserver.HttpServer;
import java.net.InetSocketAddress;
import org.junit.jupiter.api.AfterEach;
import org.junit.jupiter.api.Test;

class AgentTranscriptClientTests {

	private HttpServer server;

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
