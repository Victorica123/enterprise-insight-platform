package com.example.videoplatform.auth;

import java.time.Instant;
import java.util.Map;
import java.util.concurrent.ConcurrentHashMap;
import org.springframework.boot.autoconfigure.condition.ConditionalOnProperty;
import org.springframework.stereotype.Component;

/** 进程内黑名单：Redis 关闭时的降级实现。查询时惰性清理过期条目，避免额外定时任务。 */
@Component
@ConditionalOnProperty(prefix = "app.redis", name = "enabled", havingValue = "false", matchIfMissing = true)
public class LocalTokenBlacklist implements TokenBlacklist {

	private final Map<String, Instant> revoked = new ConcurrentHashMap<>();

	@Override
	public void revoke(String jti, Instant expiry) {
		if (Instant.now().isBefore(expiry)) {
			revoked.put(jti, expiry);
		}
	}

	@Override
	public boolean isRevoked(String jti) {
		Instant expiry = revoked.get(jti);
		if (expiry == null) {
			return false;
		}
		if (Instant.now().isAfter(expiry)) {
			revoked.remove(jti, expiry);
			return false;
		}
		return true;
	}
}
