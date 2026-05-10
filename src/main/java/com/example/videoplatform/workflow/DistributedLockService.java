package com.example.videoplatform.workflow;

public interface DistributedLockService {

	/**
	 * 尝试获取锁
	 *
	 * @param key          锁的唯一标识
	 * @param expireSeconds 锁的过期时间（秒）
	 * @return true 表示获取锁成功
	 */
	boolean tryLock(String key, long expireSeconds);

	/**
	 * 释放锁
	 *
	 * @param key 锁的唯一标识
	 */
	void unlock(String key);
}
