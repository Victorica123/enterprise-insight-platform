package com.example.videoplatform.config;

import java.time.Duration;
import org.springframework.boot.context.properties.ConfigurationProperties;

@ConfigurationProperties(prefix = "app.workflow")
public class WorkflowProperties {
	private Duration staleTaskTimeout = Duration.ofHours(1);
	private Duration taskLeaseDuration = Duration.ofMinutes(15);
	private long dispatchIntervalMs = 250;
	private long dispatchClaimLeaseMs = 30_000;

	public Duration getStaleTaskTimeout() {
		return staleTaskTimeout;
	}

	public void setStaleTaskTimeout(Duration staleTaskTimeout) {
		this.staleTaskTimeout = staleTaskTimeout;
	}

	public Duration getTaskLeaseDuration() {
		return taskLeaseDuration;
	}

	public void setTaskLeaseDuration(Duration taskLeaseDuration) {
		this.taskLeaseDuration = taskLeaseDuration;
	}

	public long getDispatchIntervalMs() {
		return dispatchIntervalMs;
	}

	public void setDispatchIntervalMs(long dispatchIntervalMs) {
		this.dispatchIntervalMs = dispatchIntervalMs;
	}

	public long getDispatchClaimLeaseMs() {
		return dispatchClaimLeaseMs;
	}

	public void setDispatchClaimLeaseMs(long dispatchClaimLeaseMs) {
		this.dispatchClaimLeaseMs = dispatchClaimLeaseMs;
	}
}
