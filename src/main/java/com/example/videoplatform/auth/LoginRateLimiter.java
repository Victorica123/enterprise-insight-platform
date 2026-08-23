package com.example.videoplatform.auth;

/**
 * 登录防爆破滑动窗口限流。
 *
 * <p>实现约定：按身份（用户名）在窗口内累计尝试次数，达到上限后拒绝。
 * 两个实现按 Redis 开关条件装配——多实例部署用 Redis ZSET + Lua 保证跨实例原子；
 * 单机/无 Redis 时降级为进程内窗口。
 */
public interface LoginRateLimiter {

	/** 记录一次尝试。窗口未满返回 true；达到上限返回 false（本次也计入）。 */
	boolean tryAcquire(String identity);

	/** 登录成功后清空该身份的窗口，避免偶尔输错密码的正常用户被锁。 */
	void reset(String identity);
}
