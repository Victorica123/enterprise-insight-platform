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
	private static final long DIRECT_UPLOAD_TOKEN_SECONDS = 900;

	/** application.yml 的演示默认密钥；非 H2 环境携带它启动直接失败，防止忘配密钥裸奔上线。 */
	private static final String DEMO_SECRET = "01234567890123456789012345678901";

	private final AppProperties appProperties;

	/** 非上面 DEMO_SECRET 之外的注入字段：用于启动期校验当前是否运行在 H2 内存库上。 */
	@org.springframework.beans.factory.annotation.Value("${spring.datasource.url:}")
	private String datasourceUrl;

	public JwtService(AppProperties appProperties) {
		this.appProperties = appProperties;
	}

	/** 启动期守卫：非 H2 环境（生产/MySQL）携带默认演示密钥直接失败，防止忘配密钥裸奔上线。 */
	@jakarta.annotation.PostConstruct
	void rejectDemoSecretOutsideH2() {
		if (DEMO_SECRET.equals(appProperties.getJwt().getSecret()) && !datasourceUrl.contains(":h2:")) {
			throw new IllegalStateException(
					"检测到默认演示 JWT 密钥且未使用 H2 内存库：请配置 APP_JWT_SECRET（至少 32 位随机字符）后再启动，"
							+ "否则任何人都可伪造登录令牌。本地轻量模式（H2 profile）不受影响。");
		}
	}

	public String generateAccessToken(
			String userId, String username, String tenantId, String role, String workspaceType) {
		Instant now = Instant.now();
		return Jwts.builder()
				.issuer(appProperties.getJwt().getIssuer())
				.audience().add(appProperties.getJwt().getAudience()).and()
				.subject(userId)
				.id(java.util.UUID.randomUUID().toString()) // jti：登出黑名单的粒度
				.claim("userId", userId)
				.claim("username", username)
				.claim("tenant_id", tenantId)
				.claim("role", role)
				.claim("workspace_type", workspaceType)
				.claim("identity_version", 2)
				.claim("token_use", "access")
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
				.issuer(appProperties.getJwt().getIssuer())
				.audience().add(appProperties.getJwt().getAudience()).and()
				.subject(username)
				.claim("taskId", taskId)
				.claim("purpose", "playback")
				.issuedAt(Date.from(now))
				.expiration(Date.from(now.plusSeconds(PLAYBACK_TOKEN_SECONDS)))
				.signWith(secretKey())
				.compact();
	}

	public String generateDirectUploadToken(String username, String fileName, String storagePath) {
		Instant now = Instant.now();
		return Jwts.builder()
				.issuer(appProperties.getJwt().getIssuer())
				.audience().add(appProperties.getJwt().getAudience()).and()
				.subject(username)
				.claim("fileName", fileName)
				.claim("storagePath", storagePath)
				.claim("purpose", "direct-upload")
				.issuedAt(Date.from(now))
				.expiration(Date.from(now.plusSeconds(DIRECT_UPLOAD_TOKEN_SECONDS)))
				.signWith(secretKey())
				.compact();
	}

	public long getPlaybackTokenSeconds() {
		return PLAYBACK_TOKEN_SECONDS;
	}

	public long getDirectUploadTokenSeconds() {
		return DIRECT_UPLOAD_TOKEN_SECONDS;
	}

	public Claims parse(String token) {
		return Jwts.parser()
				.requireIssuer(appProperties.getJwt().getIssuer())
				.requireAudience(appProperties.getJwt().getAudience())
				.verifyWith(secretKey())
				.build()
				.parseSignedClaims(token)
				.getPayload();
	}

	private SecretKey secretKey() {
		return Keys.hmacShaKeyFor(appProperties.getJwt().getSecret().getBytes(StandardCharsets.UTF_8));
	}
}
