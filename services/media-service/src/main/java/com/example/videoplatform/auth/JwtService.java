package com.example.videoplatform.auth;

import com.example.videoplatform.config.AppProperties;
import io.jsonwebtoken.Claims;
import io.jsonwebtoken.JwtBuilder;
import io.jsonwebtoken.Jws;
import io.jsonwebtoken.UnsupportedJwtException;
import io.jsonwebtoken.Jwts;
import io.jsonwebtoken.security.Keys;
import java.math.BigInteger;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.charset.StandardCharsets;
import java.security.KeyFactory;
import java.security.PrivateKey;
import java.security.PublicKey;
import java.security.interfaces.RSAPublicKey;
import java.security.spec.PKCS8EncodedKeySpec;
import java.security.spec.X509EncodedKeySpec;
import java.time.Instant;
import java.util.Base64;
import java.util.Date;
import java.util.Map;
import javax.crypto.SecretKey;
import org.springframework.stereotype.Service;

@Service
public class JwtService {

	/** 播放令牌有效期：足够看完一次视频，又短到泄露后很快失效。 */
	private static final long PLAYBACK_TOKEN_SECONDS = 3600;
	private static final long DIRECT_UPLOAD_TOKEN_SECONDS = 900;

	private final AppProperties appProperties;

	public JwtService(AppProperties appProperties) {
		this.appProperties = appProperties;
	}

	/** 启动期守卫：JWT 密钥缺失、过短或有效期非法时拒绝不安全启动。 */
	@jakarta.annotation.PostConstruct
	void validateJwtConfiguration() {
		if (isRs256()) {
			privateKey();
			publicKey();
			if (appProperties.getJwt().getKeyId() == null || appProperties.getJwt().getKeyId().isBlank()) {
				throw new IllegalStateException("APP_JWT_KEY_ID 不能为空。");
			}
		} else if (isHs256()) {
			String secret = appProperties.getJwt().getSecret();
			if (secret == null || secret.isBlank() || secret.length() < 32) {
				throw new IllegalStateException(
						"APP_JWT_SECRET 必须配置至少 32 位随机字符；拒绝使用空或弱 JWT 密钥启动。");
			}
		} else {
			throw new IllegalStateException("APP_JWT_ALGORITHM 仅支持 HS256 或 RS256。");
		}
		if (appProperties.getJwt().getExpirationSeconds() <= 0) {
			throw new IllegalStateException("APP_JWT_EXPIRATION_SECONDS 必须为正数。");
		}
	}

	public String generateAccessToken(
			String userId, String username, String tenantId, String role, String workspaceType) {
		Instant now = Instant.now();
		return sign(Jwts.builder()
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
				.expiration(Date.from(now.plusSeconds(appProperties.getJwt().getExpirationSeconds()))));
	}

	/**
	 * 生成短时效播放令牌。{@code <video>} 标签无法携带 Authorization 头，
	 * 因此播放地址通过带签名的 token 查询参数鉴权（类似 CDN 预签名 URL）。
	 * 令牌绑定 taskId 与 owner，仅用于播放该视频。
	 */
	public String generatePlaybackToken(String taskId, String username) {
		return generatePlaybackToken(taskId, username, "legacy", "personal");
	}

	public String generatePlaybackToken(
			String taskId, String username, String tenantId, String workspaceType) {
		Instant now = Instant.now();
		return sign(Jwts.builder()
				.issuer(appProperties.getJwt().getIssuer())
				.audience().add(appProperties.getJwt().getAudience()).and()
				.subject(username)
				.claim("taskId", taskId)
				.claim("tenant_id", tenantId)
				.claim("workspace_type", workspaceType)
				.claim("purpose", "playback")
				.issuedAt(Date.from(now))
				.expiration(Date.from(now.plusSeconds(PLAYBACK_TOKEN_SECONDS))));
	}

	public String generateDirectUploadToken(String username, String fileName, String storagePath) {
		return generateDirectUploadToken(username, "legacy", fileName, storagePath);
	}

	public String generateDirectUploadToken(
			String username, String tenantId, String fileName, String storagePath) {
		Instant now = Instant.now();
		return sign(Jwts.builder()
				.issuer(appProperties.getJwt().getIssuer())
				.audience().add(appProperties.getJwt().getAudience()).and()
				.subject(username)
				.claim("tenant_id", tenantId)
				.claim("fileName", fileName)
				.claim("storagePath", storagePath)
				.claim("purpose", "direct-upload")
				.issuedAt(Date.from(now))
				.expiration(Date.from(now.plusSeconds(DIRECT_UPLOAD_TOKEN_SECONDS))));
	}

	public long getPlaybackTokenSeconds() {
		return PLAYBACK_TOKEN_SECONDS;
	}

	public long getDirectUploadTokenSeconds() {
		return DIRECT_UPLOAD_TOKEN_SECONDS;
	}

	public Claims parse(String token) {
		var parser = Jwts.parser()
				.requireIssuer(appProperties.getJwt().getIssuer())
				.requireAudience(appProperties.getJwt().getAudience());
		Jws<Claims> parsed = (isRs256() ? parser.verifyWith(publicKey()) : parser.verifyWith(secretKey()))
				.build().parseSignedClaims(token);
		String expected = isRs256() ? "RS256" : "HS256";
		if (!expected.equals(parsed.getHeader().getAlgorithm())) {
			throw new UnsupportedJwtException("Unexpected JWT algorithm");
		}
		return parsed.getPayload();
	}

	public Map<String, Object> publicJwks() {
		if (!isRs256()) {
			return Map.of("keys", java.util.List.of());
		}
		RSAPublicKey key = (RSAPublicKey) publicKey();
		return Map.of("keys", java.util.List.of(Map.of(
				"kty", "RSA",
				"use", "sig",
				"alg", "RS256",
				"kid", appProperties.getJwt().getKeyId(),
				"n", base64Url(key.getModulus()),
				"e", base64Url(key.getPublicExponent()))));
	}

	private String sign(JwtBuilder builder) {
		if (isRs256()) {
			return builder.header().keyId(appProperties.getJwt().getKeyId()).and()
					.signWith(privateKey(), Jwts.SIG.RS256).compact();
		}
		return builder.signWith(secretKey(), Jwts.SIG.HS256).compact();
	}

	private boolean isRs256() {
		return "RS256".equalsIgnoreCase(appProperties.getJwt().getAlgorithm());
	}

	private boolean isHs256() {
		return "HS256".equalsIgnoreCase(appProperties.getJwt().getAlgorithm());
	}

	private PrivateKey privateKey() {
		try {
			return KeyFactory.getInstance("RSA").generatePrivate(new PKCS8EncodedKeySpec(
					readPem(appProperties.getJwt().getPrivateKeyPath(), "PRIVATE KEY")));
		} catch (Exception exception) {
			throw new IllegalStateException("无法读取 APP_JWT_PRIVATE_KEY_PATH 中的 PKCS#8 RSA 私钥。", exception);
		}
	}

	private PublicKey publicKey() {
		try {
			return KeyFactory.getInstance("RSA").generatePublic(new X509EncodedKeySpec(
					readPem(appProperties.getJwt().getPublicKeyPath(), "PUBLIC KEY")));
		} catch (Exception exception) {
			throw new IllegalStateException("无法读取 APP_JWT_PUBLIC_KEY_PATH 中的 RSA 公钥。", exception);
		}
	}

	private byte[] readPem(String path, String type) throws Exception {
		if (path == null || path.isBlank()) {
			throw new IllegalArgumentException("PEM path is blank");
		}
		String pem = Files.readString(Path.of(path), StandardCharsets.UTF_8)
				.replace("-----BEGIN " + type + "-----", "")
				.replace("-----END " + type + "-----", "")
				.replaceAll("\\s", "");
		return Base64.getDecoder().decode(pem);
	}

	private String base64Url(BigInteger value) {
		byte[] bytes = value.toByteArray();
		if (bytes.length > 1 && bytes[0] == 0) {
			bytes = java.util.Arrays.copyOfRange(bytes, 1, bytes.length);
		}
		return Base64.getUrlEncoder().withoutPadding().encodeToString(bytes);
	}

	private SecretKey secretKey() {
		return Keys.hmacShaKeyFor(appProperties.getJwt().getSecret().getBytes(StandardCharsets.UTF_8));
	}
}
