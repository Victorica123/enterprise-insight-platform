package com.example.videoplatform.auth;

import static org.assertj.core.api.Assertions.assertThat;

import com.example.videoplatform.config.AppProperties;
import org.junit.jupiter.api.Test;

class LocalLoginRateLimiterTests {

	private AppProperties properties() {
		AppProperties properties = new AppProperties();
		properties.getSecurity().getLoginRateLimit().setMaxAttempts(3);
		properties.getSecurity().getLoginRateLimit().setWindowSeconds(60);
		return properties;
	}

	@Test
	void allowsAttemptsBelowLimitAndBlocksAtLimit() {
		LocalLoginRateLimiter limiter = new LocalLoginRateLimiter(properties());

		assertThat(limiter.tryAcquire("alice")).isTrue();
		assertThat(limiter.tryAcquire("alice")).isTrue();
		assertThat(limiter.tryAcquire("alice")).isTrue();
		// 窗口内第 4 次尝试被拒
		assertThat(limiter.tryAcquire("alice")).isFalse();
	}

	@Test
	void identitiesAreIsolated() {
		LocalLoginRateLimiter limiter = new LocalLoginRateLimiter(properties());

		assertThat(limiter.tryAcquire("alice")).isTrue();
		assertThat(limiter.tryAcquire("alice")).isTrue();
		assertThat(limiter.tryAcquire("alice")).isTrue();

		// bob 的窗口不受 alice 影响
		assertThat(limiter.tryAcquire("bob")).isTrue();
	}

	@Test
	void resetClearsWindowForSuccessfulLogin() {
		LocalLoginRateLimiter limiter = new LocalLoginRateLimiter(properties());

		assertThat(limiter.tryAcquire("alice")).isTrue();
		assertThat(limiter.tryAcquire("alice")).isTrue();
		limiter.reset("alice");

		// 登录成功后清零，正常用户偶尔输错不会被锁
		assertThat(limiter.tryAcquire("alice")).isTrue();
		assertThat(limiter.tryAcquire("alice")).isTrue();
		assertThat(limiter.tryAcquire("alice")).isTrue();
		assertThat(limiter.tryAcquire("alice")).isFalse();
	}
}
