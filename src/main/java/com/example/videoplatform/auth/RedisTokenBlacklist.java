package com.example.videoplatform.auth;

import java.time.Duration;
import java.time.Instant;
import org.springframework.boot.autoconfigure.condition.ConditionalOnProperty;
import org.springframework.data.redis.core.StringRedisTemplate;
import org.springframework.stereotype.Component;

/** Redis 黑名单：SET NX + EXPIRE，多实例共享，TTL 与令牌剩余寿命一致，自动清理。 */
@Component
@ConditionalOnProperty(prefix = "app.redis", name = "enabled", havingValue = "true")
public class RedisTokenBlacklist implements TokenBlacklist {

	private static final String KEY_PREFIX = "jwt:blacklist:";

	private final StringRedisTemplate redisTemplate;

	public RedisTokenBlacklist(StringRedisTemplate redisTemplate) {
		this.redisTemplate = redisTemplate;
	}

	@Override
	public void revoke(String jti, Instant expiry) {
		Duration ttl = Duration.between(Instant.now(), expiry);
		if (ttl.isNegative() || ttl.isZero()) {
			return; // 已过期的令牌无需拉黑
		}
		redisTemplate.opsForValue().set(KEY_PREFIX + jti, "1", ttl);
	}

	@Override
	public boolean isRevoked(String jti) {
		return Boolean.TRUE.equals(redisTemplate.hasKey(KEY_PREFIX + jti));
	}
}
