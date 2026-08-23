package com.example.videoplatform.auth;

import java.util.UUID;

import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class AuthService {

	private final UserAccountRepository userRepository;
	private final PasswordEncoder passwordEncoder;
	private final JwtService jwtService;
	private final LoginRateLimiter loginRateLimiter;
	private final com.example.videoplatform.config.AppProperties appProperties;

	public AuthService(UserAccountRepository userRepository, PasswordEncoder passwordEncoder, JwtService jwtService,
			LoginRateLimiter loginRateLimiter, com.example.videoplatform.config.AppProperties appProperties) {
		this.userRepository = userRepository;
		this.passwordEncoder = passwordEncoder;
		this.jwtService = jwtService;
		this.loginRateLimiter = loginRateLimiter;
		this.appProperties = appProperties;
	}

	@Transactional
	public AuthDtos.AuthResponse register(AuthDtos.RegisterRequest request) {
		if (userRepository.existsByUsername(request.username())) {
			throw new IllegalArgumentException("用户名已存在");
		}
		UserAccount user = new UserAccount(UUID.randomUUID().toString(), request.username(), passwordEncoder.encode(request.password()));
		userRepository.save(user);
		return new AuthDtos.AuthResponse(user.getUserId(), user.getUsername(), jwtService.generateToken(user.getUserId(), user.getUsername()));
	}

	/**
	 * 登录前先过滑动窗口限流（按用户名），防爆破枚举。命中上限直接 429，不做密码比对——
	 * 否则攻击者可以用「触发限流的用户名」探测 BCrypt 校验耗时差异。
	 */
	@Transactional(readOnly = true)
	public AuthDtos.AuthResponse login(AuthDtos.LoginRequest request) {
		var limit = appProperties.getSecurity().getLoginRateLimit();
		if (!loginRateLimiter.tryAcquire(request.username())) {
			throw new RateLimitExceededException(limit.getMaxAttempts(), limit.getWindowSeconds());
		}
		UserAccount user = userRepository.findByUsername(request.username())
				.orElseThrow(() -> new IllegalArgumentException("用户名或密码错误"));
		if (!passwordEncoder.matches(request.password(), user.getPasswordHash())) {
			throw new IllegalArgumentException("用户名或密码错误");
		}
		loginRateLimiter.reset(request.username());
		return new AuthDtos.AuthResponse(user.getUserId(), user.getUsername(), jwtService.generateToken(user.getUserId(), user.getUsername()));
	}
}
