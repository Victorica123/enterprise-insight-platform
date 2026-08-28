package com.example.videoplatform.auth;

/** 登录尝试超出滑动窗口上限。全局处理为 429，与业务参数错误（400）区分开。 */
public class RateLimitExceededException extends RuntimeException {

	private final int windowSeconds;

	public RateLimitExceededException(int maxAttempts, int windowSeconds) {
		super("登录尝试过于频繁，请 " + windowSeconds + " 秒后再试");
		this.windowSeconds = windowSeconds;
	}

	public int getWindowSeconds() {
		return windowSeconds;
	}
}
