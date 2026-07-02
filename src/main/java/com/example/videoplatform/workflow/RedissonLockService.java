package com.example.videoplatform.workflow;

import java.util.concurrent.TimeUnit;
import org.redisson.api.RLock;
import org.redisson.api.RedissonClient;
import org.springframework.boot.autoconfigure.condition.ConditionalOnProperty;
import org.springframework.stereotype.Service;

@Service
@ConditionalOnProperty(prefix = "app.redis", name = "enabled", havingValue = "true")
public class RedissonLockService implements DistributedLockService {

	private final RedissonClient redissonClient;

	public RedissonLockService(RedissonClient redissonClient) {
		this.redissonClient = redissonClient;
	}

	@Override
	public boolean tryLock(String key, long expireSeconds) {
		RLock lock = redissonClient.getLock(key);
		try {
			// 非阻塞获取（waitTime=0）：锁已被占用时立即返回 false，用于合并等操作的重复提交保护。
			// leaseTime=expireSeconds：持有者宕机时锁到期自动释放，避免死锁。
			// 说明：显式指定 leaseTime 会关闭 Redisson 看门狗自动续期，从而与 Redis 兜底实现
			// （setIfAbsent + TTL）保持一致的语义：expireSeconds 是租约时间，而非等待时间。
			return lock.tryLock(0, expireSeconds, TimeUnit.SECONDS);
		} catch (InterruptedException e) {
			Thread.currentThread().interrupt();
			return false;
		}
	}

	@Override
	public boolean tryLockWithWatchdog(String key) {
		RLock lock = redissonClient.getLock(key);
		try {
			// 不传 leaseTime → 启用 Redisson 看门狗：持有者存活期间锁自动续期，
			// 使锁能安全横跨分钟级的转码/转写/摘要，不会中途过期被他人抢占。
			// waitTime=0 → 非阻塞，抢不到立即返回 false（交由 fan-out 完成，不占用线程）。
			return lock.tryLock(0, TimeUnit.SECONDS);
		} catch (InterruptedException e) {
			Thread.currentThread().interrupt();
			return false;
		}
	}

	@Override
	public void unlock(String key) {
		RLock lock = redissonClient.getLock(key);
		// 只有当前线程持有锁时才释放，避免误释放其他线程的锁
		if (lock.isHeldByCurrentThread()) {
			lock.unlock();
		}
	}
}
