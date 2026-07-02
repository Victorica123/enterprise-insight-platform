package com.example.videoplatform.auth;

import com.example.videoplatform.config.AppProperties;
import io.jsonwebtoken.Claims;
import io.jsonwebtoken.Jwts;
import io.jsonwebtoken.security.Keys;
import java.nio.charset.StandardCharsets;
import java.time.Instant;
import java.util.Date;
import javax.crypto.SecretKey;
import org.springframework.stereotype.Service;

@Service
public class JwtService {

	/** 播放令牌有效期：足够看完一次视频，又短到泄露后很快失效。 */
	private static final long PLAYBACK_TOKEN_SECONDS = 3600;

	private final AppProperties appProperties;

	public JwtService(AppProperties appProperties) {
		this.appProperties = appProperties;
	}

	public String generateToken(String userId, String username) {
		Instant now = Instant.now();
		return Jwts.builder()
				.subject(username)
				.claim("userId", userId)
				.issuedAt(Date.from(now))
				.expiration(Date.from(now.plusSeconds(appProperties.getJwt().getExpirationSeconds())))
				.signWith(secretKey())
				.compact();
	}

	/**
	 * 生成短时效播放令牌。{@code <video>} 标签无法携带 Authorization 头，
	 * 因此播放地址通过带签名的 token 查询参数鉴权（类似 CDN 预签名 URL）。
	 * 令牌绑定 taskId 与 owner，仅用于播放该视频。
	 */
	public String generatePlaybackToken(String taskId, String username) {
		Instant now = Instant.now();
		return Jwts.builder()
				.subject(username)
				.claim("taskId", taskId)
				.claim("purpose", "playback")
				.issuedAt(Date.from(now))
				.expiration(Date.from(now.plusSeconds(PLAYBACK_TOKEN_SECONDS)))
				.signWith(secretKey())
				.compact();
	}

	public long getPlaybackTokenSeconds() {
		return PLAYBACK_TOKEN_SECONDS;
	}

	public Claims parse(String token) {
		return Jwts.parser().verifyWith(secretKey()).build().parseSignedClaims(token).getPayload();
	}

	private SecretKey secretKey() {
		return Keys.hmacShaKeyFor(appProperties.getJwt().getSecret().getBytes(StandardCharsets.UTF_8));
	}
}
