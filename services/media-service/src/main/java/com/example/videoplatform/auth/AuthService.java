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
	private final WorkspaceService workspaceService;

	public AuthService(UserAccountRepository userRepository, PasswordEncoder passwordEncoder, JwtService jwtService,
			LoginRateLimiter loginRateLimiter, com.example.videoplatform.config.AppProperties appProperties,
			WorkspaceService workspaceService) {
		this.userRepository = userRepository;
		this.passwordEncoder = passwordEncoder;
		this.jwtService = jwtService;
		this.loginRateLimiter = loginRateLimiter;
		this.appProperties = appProperties;
		this.workspaceService = workspaceService;
	}

	@Transactional
	public AuthDtos.AuthResponse register(AuthDtos.RegisterRequest request) {
		if (userRepository.existsByUsername(request.username())) {
			throw new IllegalArgumentException("用户名已存在");
		}
		UserAccount user = new UserAccount(UUID.randomUUID().toString(), request.username(), passwordEncoder.encode(request.password()));
		// 手工分配 ID 的实体会走 JPA merge；必须继续使用 save 返回的受管实例，
		// 否则随后写入的 primaryTenantId 只停留在 detached 对象上。
		user = userRepository.save(user);
		WorkspaceService.WorkspaceContext workspace = workspaceService.ensurePersonalWorkspace(user);
		return response(user, workspace);
	}

	/**
	 * 登录前先过滑动窗口限流（按用户名），防爆破枚举。命中上限直接 429，不做密码比对——
	 * 否则攻击者可以用「触发限流的用户名」探测 BCrypt 校验耗时差异。
	 */
	@Transactional
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
		WorkspaceService.WorkspaceContext workspace = workspaceService.ensurePersonalWorkspace(user);
		return response(user, workspace);
	}

	@Transactional(readOnly = true)
	public AuthDtos.AuthResponse switchWorkspace(String userId, String tenantId) {
		UserAccount user = userRepository.findById(userId)
				.orElseThrow(() -> new org.springframework.web.server.ResponseStatusException(
						org.springframework.http.HttpStatus.NOT_FOUND, "用户不存在"));
		return response(user, workspaceService.requireContext(userId, tenantId));
	}

	private AuthDtos.AuthResponse response(UserAccount user, WorkspaceService.WorkspaceContext workspace) {
		String token = jwtService.generateAccessToken(
				user.getUserId(), user.getUsername(), workspace.tenantId(),
				workspace.jwtRole(), workspace.workspaceType());
		return new AuthDtos.AuthResponse(
				user.getUserId(), user.getUsername(), workspace.tenantId(),
				workspace.jwtRole(), workspace.workspaceType(), token);
	}
}
