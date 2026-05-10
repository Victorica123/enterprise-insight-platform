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

	public Claims parse(String token) {
		return Jwts.parser().verifyWith(secretKey()).build().parseSignedClaims(token).getPayload();
	}

	private SecretKey secretKey() {
		return Keys.hmacShaKeyFor(appProperties.getJwt().getSecret().getBytes(StandardCharsets.UTF_8));
	}
}
