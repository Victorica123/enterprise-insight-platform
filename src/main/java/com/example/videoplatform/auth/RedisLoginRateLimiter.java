package com.example.videoplatform.auth;

import com.example.videoplatform.config.AppProperties;
import java.time.Duration;
import java.util.List;
import org.springframework.boot.autoconfigure.condition.ConditionalOnProperty;
import org.springframework.data.redis.core.StringRedisTemplate;
import org.springframework.data.redis.core.script.DefaultRedisScript;
import org.springframework.stereotype.Component;

/**
 * Redis 滑动窗口限流：ZSET 记录窗口内每次尝试的时间戳，Lua 保证「清理旧记录 + 计数 + 写入」原子执行。
 *
 * <p>为什么用 Lua：拆成多条命令时，并发下的 ZCARD 都读到旧值，两个实例会同时放行超额请求；
 * Redis 单线程执行脚本期间不会插入其他命令，天然规避竞态。
 */
@Component
@ConditionalOnProperty(prefix = "app.redis", name = "enabled", havingValue = "true")
public class RedisLoginRateLimiter implements LoginRateLimiter {

	private static final String KEY_PREFIX = "ratelimit:login:";

	/** KEYS[1]=zset key；ARGV：nowMs / windowMs / limit / member */
	private static final DefaultRedisScript<Long> SLIDING_WINDOW = new DefaultRedisScript<>("""
			redis.call('ZREMRANGEBYSCORE', KEYS[1], 0, tonumber(ARGV[1]) - tonumber(ARGV[2]))
			local count = redis.call('ZCARD', KEYS[1])
			if count < tonumber(ARGV[3]) then
				redis.call('ZADD', KEYS[1], ARGV[1], ARGV[4])
				redis.call('PEXPIRE', KEYS[1], ARGV[2])
				return 1
			end
			return 0
			""", Long.class);

	private final StringRedisTemplate redisTemplate;
	private final int maxAttempts;
	private final Duration window;

	public RedisLoginRateLimiter(StringRedisTemplate redisTemplate, AppProperties appProperties) {
		this.redisTemplate = redisTemplate;
		this.maxAttempts = appProperties.getSecurity().getLoginRateLimit().getMaxAttempts();
		this.window = Duration.ofSeconds(appProperties.getSecurity().getLoginRateLimit().getWindowSeconds());
	}

	@Override
	public boolean tryAcquire(String identity) {
		String member = Thread.currentThread().getId() + "-" + System.nanoTime();
		Long allowed = redisTemplate.execute(SLIDING_WINDOW,
				List.of(KEY_PREFIX + identity),
				String.valueOf(System.currentTimeMillis()),
				String.valueOf(window.toMillis()),
				String.valueOf(maxAttempts),
				member);
		return allowed != null && allowed == 1L;
	}

	@Override
	public void reset(String identity) {
		redisTemplate.delete(KEY_PREFIX + identity);
	}
}
