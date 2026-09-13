package com.example.videoplatform.config;

import org.springframework.boot.context.properties.ConfigurationProperties;

@ConfigurationProperties(prefix = "app.integration")
public class IntegrationProperties {
	private final Agent agent = new Agent();

	public Agent getAgent() {
		return agent;
	}

	public static class Agent extends FeatureProperties {
		private String baseUrl = "http://127.0.0.1:8000";
		private String serviceToken;
		private long dispatchIntervalMs = 2_000;
		private int maxAttempts = 10;
		private long claimLeaseDurationMs = 30_000;
		private int circuitFailureThreshold = 3;
		private long circuitOpenMs = 30_000;
		private long circuitMaxOpenMs = 300_000;

		public int getCircuitFailureThreshold() { return circuitFailureThreshold; }
		public void setCircuitFailureThreshold(int value) { circuitFailureThreshold = value; }
		public long getCircuitOpenMs() { return circuitOpenMs; }
		public void setCircuitOpenMs(long value) { circuitOpenMs = value; }
		public long getCircuitMaxOpenMs() { return circuitMaxOpenMs; }
		public void setCircuitMaxOpenMs(long value) { circuitMaxOpenMs = value; }

		public String getBaseUrl() {
			return baseUrl;
		}

		public void setBaseUrl(String baseUrl) {
			this.baseUrl = baseUrl;
		}

		public String getServiceToken() {
			return serviceToken;
		}

		public void setServiceToken(String serviceToken) {
			this.serviceToken = serviceToken;
		}

		public long getDispatchIntervalMs() {
			return dispatchIntervalMs;
		}

		public void setDispatchIntervalMs(long dispatchIntervalMs) {
			this.dispatchIntervalMs = dispatchIntervalMs;
		}

		public int getMaxAttempts() {
			return maxAttempts;
		}

		public void setMaxAttempts(int maxAttempts) {
			this.maxAttempts = maxAttempts;
		}

		public long getClaimLeaseDurationMs() {
			return claimLeaseDurationMs;
		}

		public void setClaimLeaseDurationMs(long claimLeaseDurationMs) {
			this.claimLeaseDurationMs = claimLeaseDurationMs;
		}
	}
}
