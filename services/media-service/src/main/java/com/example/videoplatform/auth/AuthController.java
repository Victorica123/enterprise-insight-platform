package com.example.videoplatform.auth;

import com.example.videoplatform.common.ApiResponse;
import io.jsonwebtoken.Claims;
import jakarta.servlet.http.HttpServletRequest;
import jakarta.validation.Valid;
import org.springframework.http.HttpStatus;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RequestHeader;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.server.ResponseStatusException;

@RestController
@RequestMapping("/api/auth")
public class AuthController {

	private final AuthService authService;
	private final JwtService jwtService;
	private final TokenBlacklist tokenBlacklist;
	private final com.example.videoplatform.config.AppProperties appProperties;

	public AuthController(AuthService authService, JwtService jwtService, TokenBlacklist tokenBlacklist,
			com.example.videoplatform.config.AppProperties appProperties) {
		this.authService = authService;
		this.jwtService = jwtService;
		this.tokenBlacklist = tokenBlacklist;
		this.appProperties = appProperties;
	}

	@PostMapping("/register")
	public ApiResponse<AuthDtos.AuthResponse> register(@Valid @RequestBody AuthDtos.RegisterRequest request) {
		requireLocalAuthEnabled();
		return ApiResponse.ok(authService.register(request));
	}

	@PostMapping("/login")
	public ApiResponse<AuthDtos.AuthResponse> login(@Valid @RequestBody AuthDtos.LoginRequest request) {
		requireLocalAuthEnabled();
		return ApiResponse.ok(authService.login(request));
	}

	@GetMapping("/jwks")
	public java.util.Map<String, Object> jwks() {
		return jwtService.publicJwks();
	}

	@PostMapping("/oidc/exchange")
	public ApiResponse<AuthDtos.AuthResponse> exchangeOidc(
			HttpServletRequest request,
			@RequestHeader(value = "X-Workspace-Id", required = false) String workspaceId) {
		String header = request.getHeader("Authorization");
		if (header == null || !header.startsWith("Bearer ") || header.length() <= 7) {
			throw new ResponseStatusException(HttpStatus.BAD_REQUEST, "缺少 OIDC Bearer 令牌");
		}
		return ApiResponse.ok(authService.loginOidc(header.substring(7), workspaceId));
	}

	private void requireLocalAuthEnabled() {
		if (!appProperties.getSecurity().isLocalAuthEnabled()) {
			throw new ResponseStatusException(HttpStatus.NOT_FOUND, "本地账号登录未启用");
		}
	}

	/**
	 * 登出：把当前 Bearer 令牌的 jti 拉黑至其自然过期时间。
	 * JWT 本身无状态不可撤回，登出的服务端语义 = 黑名单兜底 + 客户端丢弃令牌。
	 */
	@PostMapping("/logout")
	public ApiResponse<Void> logout(HttpServletRequest request) {
		String header = request.getHeader("Authorization");
		if (header == null || !header.startsWith("Bearer ")) {
			throw new ResponseStatusException(HttpStatus.BAD_REQUEST, "缺少 Bearer 令牌");
		}
		try {
			Claims claims = jwtService.parse(header.substring(7));
			tokenBlacklist.revoke(claims.getId(), claims.getExpiration().toInstant());
			return ApiResponse.ok(null);
		} catch (io.jsonwebtoken.JwtException expired) {
			// 已过期令牌无需拉黑，直接视为登出成功（幂等）
			return ApiResponse.ok(null);
		}
	}
}
