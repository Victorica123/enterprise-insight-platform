package com.example.videoplatform.auth;

import java.time.Instant;

/**
 * JWT 登出黑名单：JWT 无状态、签发后无法撤回，登出只能靠服务端记录 jti 至令牌自然过期。
 * 只存 jti + 过期时间，不存敏感载荷；过期后条目自动失效，黑名单体积以「登出次数 × 令牌剩余寿命」为上界。
 */
public interface TokenBlacklist {

	/** 将令牌的 jti 拉黑至 expiry（即令牌自身的 exp）。 */
	void revoke(String jti, Instant expiry);

	/** jti 被拉黑且尚未过期时返回 true。 */
	boolean isRevoked(String jti);
}
