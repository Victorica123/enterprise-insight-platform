package com.example.videoplatform.auth;

import static org.assertj.core.api.Assertions.assertThat;

import com.example.videoplatform.config.AppProperties;
import java.util.concurrent.atomic.AtomicLong;
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

	@Test
	void globallyEvictsInactiveIdentitiesAfterWindowExpires() {
		AtomicLong now = new AtomicLong(1_000L);
		LocalLoginRateLimiter limiter = new LocalLoginRateLimiter(3, 1_000L, now::get);
		for (int index = 0; index < 1_000; index++) {
			assertThat(limiter.tryAcquire("bot-" + index)).isTrue();
		}
		assertThat(limiter.entryCount()).isEqualTo(1_000);

		now.addAndGet(2_000L);
		assertThat(limiter.tryAcquire("current-user")).isTrue();

		assertThat(limiter.entryCount()).isEqualTo(1);
	}
}
