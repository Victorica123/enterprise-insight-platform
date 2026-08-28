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
	 * 尝试获取锁（非阻塞），并对长任务启用自动续期。
	 *
	 * <p>用于横跨分钟级处理（转码 / 转写 / 摘要）的单飞场景：固定 TTL 的锁会在处理途中过期，
	 * 导致另一个 worker 误以为无人处理而重复执行。Redisson 实现通过看门狗（持有者存活即
	 * 每 ~10s 自动续期）避免这一点；Redis 兜底实现无看门狗，退化为一个较长的固定租约；
	 * 本地实现为 JVM 内可重入锁，无过期问题。
	 *
	 * @param key 锁的唯一标识
	 * @return true 表示获取成功；false 表示已被其他线程/节点持有
	 */
	boolean tryLockWithWatchdog(String key);

	/**
	 * 释放锁
	 *
	 * @param key 锁的唯一标识
	 */
	void unlock(String key);
}
