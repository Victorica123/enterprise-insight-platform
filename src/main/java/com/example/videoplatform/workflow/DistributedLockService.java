package com.example.videoplatform.workflow;

public interface DistributedLockService {

	/**
	 * 尝试获取锁（非阻塞，立即返回，不等待）。
	 *
	 * <p>两个实现（Redisson / Redis 兜底）对本方法保持一致语义：锁被占用时立即返回
	 * {@code false}；获取成功后到达租约期自动释放，避免持有者异常退出导致死锁。
	 *
	 * @param key           锁的唯一标识
	 * @param expireSeconds 锁的租约时间（秒）：持有者未显式释放时到期自动释放
	 * @return true 表示获取锁成功；false 表示锁已被其他线程/节点占用
	 */
	boolean tryLock(String key, long expireSeconds);

	/**
	 * 释放锁
	 *
	 * @param key 锁的唯一标识
	 */
	void unlock(String key);
}
