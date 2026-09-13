package com.example.videoplatform.config;

import org.springframework.boot.context.properties.ConfigurationProperties;

@ConfigurationProperties(prefix = "app.security")
public class SecurityProperties {
	private final LoginRateLimit loginRateLimit = new LoginRateLimit();
	private boolean localAuthEnabled = true;

	public LoginRateLimit getLoginRateLimit() {
		return loginRateLimit;
	}

	public boolean isLocalAuthEnabled() {
		return localAuthEnabled;
	}

	public void setLocalAuthEnabled(boolean localAuthEnabled) {
		this.localAuthEnabled = localAuthEnabled;
	}

	/** 滑动窗口：窗口内失败次数达到上限后拒绝，窗口滑出后自动恢复。 */
	public static class LoginRateLimit {
		private int maxAttempts = 5;
		private int windowSeconds = 300;

		public int getMaxAttempts() {
			return maxAttempts;
		}

		public void setMaxAttempts(int maxAttempts) {
			this.maxAttempts = maxAttempts;
		}

		public int getWindowSeconds() {
			return windowSeconds;
		}

		public void setWindowSeconds(int windowSeconds) {
			this.windowSeconds = windowSeconds;
		}
	}
}
