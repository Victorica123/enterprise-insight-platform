package com.example.videoplatform.auth;

import com.example.videoplatform.config.AppProperties;
import java.time.Duration;
import java.util.ArrayDeque;
import java.util.Deque;
import java.util.Map;
import java.util.concurrent.ConcurrentHashMap;
import java.util.concurrent.atomic.AtomicBoolean;
import java.util.concurrent.atomic.AtomicLong;
import java.util.function.LongSupplier;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.autoconfigure.condition.ConditionalOnProperty;
import org.springframework.stereotype.Component;

/**
 * 进程内滑动窗口限流：Redis 关闭时的降级实现（单实例语义）。
 * 每身份一个时间戳队列，读取时惰性淘汰过期项；synchronized 只锁单个身份，互不影响。
 */
@Component
@ConditionalOnProperty(prefix = "app.redis", name = "enabled", havingValue = "false", matchIfMissing = true)
public class LocalLoginRateLimiter implements LoginRateLimiter {

	private final Map<String, Deque<Long>> attempts = new ConcurrentHashMap<>();
	private final int maxAttempts;
	private final long windowMillis;
	private final long cleanupIntervalMillis;
	private final LongSupplier clock;
	private final AtomicLong nextCleanupAt = new AtomicLong();

	@Autowired
	public LocalLoginRateLimiter(AppProperties appProperties) {
		this(appProperties.getSecurity().getLoginRateLimit().getMaxAttempts(),
				Duration.ofSeconds(appProperties.getSecurity().getLoginRateLimit().getWindowSeconds()).toMillis(),
				System::currentTimeMillis);
	}

	LocalLoginRateLimiter(int maxAttempts, long windowMillis, LongSupplier clock) {
		this.maxAttempts = maxAttempts;
		this.windowMillis = windowMillis;
		this.cleanupIntervalMillis = Math.max(1_000L, Math.min(60_000L, Math.max(1L, windowMillis)));
		this.clock = clock;
	}

	@Override
	public boolean tryAcquire(String identity) {
		long now = clock.getAsLong();
		cleanupExpiredWindows(now);
		AtomicBoolean acquired = new AtomicBoolean();
		attempts.compute(identity, (key, existing) -> {
			Deque<Long> window = existing == null ? new ArrayDeque<>() : existing;
			removeExpired(window, now);
			if (window.size() < maxAttempts) {
				window.addLast(now);
				acquired.set(true);
			}
			return window.isEmpty() ? null : window;
		});
		return acquired.get();
	}

	@Override
	public void reset(String identity) {
		attempts.remove(identity);
	}

	private void cleanupExpiredWindows(long now) {
		long scheduled = nextCleanupAt.get();
		if (now < scheduled || !nextCleanupAt.compareAndSet(scheduled, now + cleanupIntervalMillis)) {
			return;
		}
		attempts.forEach((identity, ignored) -> attempts.computeIfPresent(identity, (key, window) -> {
			removeExpired(window, now);
			return window.isEmpty() ? null : window;
		}));
	}

	private void removeExpired(Deque<Long> window, long now) {
		while (!window.isEmpty() && now - window.peekFirst() >= windowMillis) {
			window.removeFirst();
		}
	}

	int entryCount() {
		return attempts.size();
	}
}
