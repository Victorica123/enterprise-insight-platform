package com.example.videoplatform.auth;

import io.jsonwebtoken.Claims;
import jakarta.servlet.FilterChain;
import jakarta.servlet.ServletException;
import jakarta.servlet.http.HttpServletRequest;
import jakarta.servlet.http.HttpServletResponse;
import java.io.IOException;
import java.util.List;
import org.springframework.security.authentication.UsernamePasswordAuthenticationToken;
import org.springframework.security.core.authority.SimpleGrantedAuthority;
import org.springframework.security.core.context.SecurityContextHolder;
import org.springframework.security.web.authentication.WebAuthenticationDetailsSource;
import org.springframework.stereotype.Component;
import org.springframework.web.filter.OncePerRequestFilter;

@Component
public class JwtAuthenticationFilter extends OncePerRequestFilter {

	private final JwtService jwtService;
	private final TokenBlacklist tokenBlacklist;

	public JwtAuthenticationFilter(JwtService jwtService, TokenBlacklist tokenBlacklist) {
		this.jwtService = jwtService;
		this.tokenBlacklist = tokenBlacklist;
	}

	@Override
	protected void doFilterInternal(HttpServletRequest request, HttpServletResponse response, FilterChain filterChain)
			throws ServletException, IOException {
		String header = request.getHeader("Authorization");
		if (header != null && header.startsWith("Bearer ")) {
			try {
				Claims claims = jwtService.parse(header.substring(7));
				// 带 purpose 的短时效令牌（播放/直传）只服务各自场景，不得当作登录凭证访问 API
				if (claims.get("purpose") == null
						// 登出黑名单：jti 命中即视为未认证（过期条目由黑名单实现自动清理）
						&& !tokenBlacklist.isRevoked(claims.getId())) {
					// principal 用不可变的 userId（与 owner/findByUserId 全链路语义一致），
					// 避免 username/userId 不一致导致真实登录用户上传报“用户不存在”
					String principal = claims.getSubject();
					String role = claims.get("role", String.class);
					String authority = role == null || role.isBlank() ? "ROLE_USER" : "ROLE_" + role.toUpperCase();
					UsernamePasswordAuthenticationToken auth = new UsernamePasswordAuthenticationToken(
							principal, null, List.of(new SimpleGrantedAuthority(authority)));
					auth.setDetails(new WebAuthenticationDetailsSource().buildDetails(request));
					SecurityContextHolder.getContext().setAuthentication(auth);
				}
			} catch (Exception e) {
				// token invalid or expired — leave context unauthenticated
			}
		}
		filterChain.doFilter(request, response);
	}
}
