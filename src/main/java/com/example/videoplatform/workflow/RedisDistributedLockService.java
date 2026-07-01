package com.example.videoplatform.workflow;

import java.nio.charset.StandardCharsets;
import java.util.UUID;
import org.springframework.boot.autoconfigure.condition.ConditionalOnMissingBean;
import org.springframework.boot.autoconfigure.condition.ConditionalOnProperty;
import org.springframework.data.redis.core.StringRedisTemplate;
import org.springframework.data.redis.core.script.DefaultRedisScript;
import org.springframework.stereotype.Service;

@Service
@ConditionalOnProperty(prefix = "app.redis", name = "enabled", havingValue = "true")
@ConditionalOnMissingBean(org.redisson.api.RedissonClient.class)
public class RedisDistributedLockService implements DistributedLockService {

	private static final String UNLOCK_SCRIPT =
			"if redis.call('get', KEYS[1]) == ARGV[1] then " +
					"return redis.call('del', KEYS[1]) " +
					"else return 0 end";

	private final StringRedisTemplate redisTemplate;
	private final ThreadLocal<String> lockValueHolder = new ThreadLocal<>();

	public RedisDistributedLockService(StringRedisTemplate redisTemplate) {
		this.redisTemplate = redisTemplate;
	}

	@Override
	public boolean tryLock(String key, long expireSeconds) {
		String lockValue = UUID.randomUUID().toString();
		Boolean success = redisTemplate.opsForValue()
				.setIfAbsent(key, lockValue, java.time.Duration.ofSeconds(expireSeconds));
		if (Boolean.TRUE.equals(success)) {
			lockValueHolder.set(lockValue);
			return true;
		}
		return false;
	}

	@Override
	public void unlock(String key) {
		String lockValue = lockValueHolder.get();
		if (lockValue == null) {
			return;
		}
		DefaultRedisScript<Long> script = new DefaultRedisScript<>();
		script.setScriptText(UNLOCK_SCRIPT);
		script.setResultType(Long.class);
		redisTemplate.execute(script, java.util.List.of(key), lockValue);
		lockValueHolder.remove();
	}
}
