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

	/** 兜底实现无看门狗，长任务锁用一个较长的固定租约（10 分钟）尽量覆盖处理时长。 */
	private static final long WATCHDOG_FALLBACK_LEASE_SECONDS = 600;

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
	public boolean tryLockWithWatchdog(String key) {
		// 无看门狗，退化为较长固定租约。unlock 语义与 tryLock 一致（ThreadLocal 持有 lockValue）。
		return tryLock(key, WATCHDOG_FALLBACK_LEASE_SECONDS);
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
