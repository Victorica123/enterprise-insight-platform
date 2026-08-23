package com.example.videoplatform.auth;

import com.example.videoplatform.config.AppProperties;
import java.time.Duration;
import java.util.ArrayDeque;
import java.util.Deque;
import java.util.Map;
import java.util.concurrent.ConcurrentHashMap;
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

	public LocalLoginRateLimiter(AppProperties appProperties) {
		this.maxAttempts = appProperties.getSecurity().getLoginRateLimit().getMaxAttempts();
		this.windowMillis = Duration.ofSeconds(appProperties.getSecurity().getLoginRateLimit().getWindowSeconds())
				.toMillis();
	}

	@Override
	public boolean tryAcquire(String identity) {
		long now = System.currentTimeMillis();
		Deque<Long> window = attempts.computeIfAbsent(identity, key -> new ArrayDeque<>());
		synchronized (window) {
			while (!window.isEmpty() && now - window.peekFirst() >= windowMillis) {
				window.removeFirst();
			}
			if (window.size() >= maxAttempts) {
				return false;
			}
			window.addLast(now);
			return true;
		}
	}

	@Override
	public void reset(String identity) {
		attempts.remove(identity);
	}
}
