package com.example.videoplatform.workflow;

import java.util.Map;
import java.util.concurrent.ConcurrentHashMap;
import java.util.concurrent.locks.ReentrantLock;
import org.springframework.boot.autoconfigure.condition.ConditionalOnProperty;
import org.springframework.stereotype.Service;

@Service
@ConditionalOnProperty(prefix = "app.redis", name = "enabled", havingValue = "false", matchIfMissing = true)
public class LocalLockService implements DistributedLockService {

	private final Map<String, ReentrantLock> locks = new ConcurrentHashMap<>();

	@Override
	public boolean tryLock(String key, long expireSeconds) {
		ReentrantLock lock = locks.computeIfAbsent(key, k -> new ReentrantLock());
		return lock.tryLock();
	}

	@Override
	public void unlock(String key) {
		ReentrantLock lock = locks.get(key);
		if (lock != null && lock.isHeldByCurrentThread()) {
			lock.unlock();
		}
	}
}
