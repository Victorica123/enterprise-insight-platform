package com.example.videoplatform.workflow;

import java.util.concurrent.ConcurrentHashMap;
import java.util.concurrent.ConcurrentMap;
import java.util.concurrent.locks.ReentrantLock;
import org.springframework.boot.autoconfigure.condition.ConditionalOnProperty;
import org.springframework.stereotype.Service;

@Service
@ConditionalOnProperty(prefix = "app.redis", name = "enabled", havingValue = "false", matchIfMissing = true)
public class LocalLockService implements DistributedLockService {

	private final ConcurrentMap<String, LockEntry> locks = new ConcurrentHashMap<>();

	@Override
	public boolean tryLock(String key, long expireSeconds) {
		LockEntry entry = locks.compute(key, (ignored, current) -> {
			LockEntry retained = current == null ? new LockEntry() : current;
			retained.references++;
			return retained;
		});
		boolean acquired = entry.lock.tryLock();
		if (!acquired) {
			releaseReference(key, entry);
		}
		return acquired;
	}

	@Override
	public boolean tryLockWithWatchdog(String key) {
		// 单 JVM 内的可重入锁，没有过期概念，看门狗语义等同于普通非阻塞加锁。
		return tryLock(key, 0);
	}

	@Override
	public void unlock(String key) {
		LockEntry entry = locks.get(key);
		if (entry != null && entry.lock.isHeldByCurrentThread()) {
			entry.lock.unlock();
			releaseReference(key, entry);
		}
	}

	private void releaseReference(String key, LockEntry expected) {
		locks.computeIfPresent(key, (ignored, current) -> {
			if (current != expected) {
				return current;
			}
			current.references--;
			return current.references == 0 ? null : current;
		});
	}

	int lockEntryCount() {
		return locks.size();
	}

	private static final class LockEntry {
		private final ReentrantLock lock = new ReentrantLock();
		private int references;
	}
}
