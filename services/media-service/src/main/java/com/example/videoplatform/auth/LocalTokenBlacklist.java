package com.example.videoplatform.auth;

import java.time.Clock;
import java.time.Instant;
import java.util.Map;
import java.util.concurrent.ConcurrentHashMap;
import java.util.concurrent.atomic.AtomicLong;
import org.springframework.boot.autoconfigure.condition.ConditionalOnProperty;
import org.springframework.stereotype.Component;

/** 进程内黑名单：Redis 关闭时的降级实现。查询时惰性清理过期条目，避免额外定时任务。 */
@Component
@ConditionalOnProperty(prefix = "app.redis", name = "enabled", havingValue = "false", matchIfMissing = true)
public class LocalTokenBlacklist implements TokenBlacklist {

	private final Map<String, Instant> revoked = new ConcurrentHashMap<>();
	private final Clock clock;
	private final AtomicLong nextCleanupAt = new AtomicLong();

	public LocalTokenBlacklist() {
		this(Clock.systemUTC());
	}

	LocalTokenBlacklist(Clock clock) {
		this.clock = clock;
	}

	@Override
	public void revoke(String jti, Instant expiry) {
		Instant now = clock.instant();
		cleanupExpired(now);
		if (now.isBefore(expiry)) {
			revoked.put(jti, expiry);
		}
	}

	@Override
	public boolean isRevoked(String jti) {
		Instant now = clock.instant();
		cleanupExpired(now);
		Instant expiry = revoked.get(jti);
		if (expiry == null) {
			return false;
		}
		if (!now.isBefore(expiry)) {
			revoked.remove(jti, expiry);
			return false;
		}
		return true;
	}

	private void cleanupExpired(Instant now) {
		long nowMillis = now.toEpochMilli();
		long scheduled = nextCleanupAt.get();
		if (nowMillis < scheduled || !nextCleanupAt.compareAndSet(scheduled, nowMillis + 60_000L)) {
			return;
		}
		revoked.entrySet().removeIf(entry -> !now.isBefore(entry.getValue()));
	}

	int entryCount() {
		return revoked.size();
	}
}
