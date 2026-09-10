package com.example.videoplatform.auth;

import com.example.videoplatform.config.AppProperties;
import jakarta.annotation.PostConstruct;
import org.springframework.http.HttpStatus;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.security.oauth2.core.DelegatingOAuth2TokenValidator;
import org.springframework.security.oauth2.core.OAuth2Error;
import org.springframework.security.oauth2.core.OAuth2TokenValidator;
import org.springframework.security.oauth2.core.OAuth2TokenValidatorResult;
import org.springframework.security.oauth2.jwt.Jwt;
import org.springframework.security.oauth2.jwt.JwtDecoder;
import org.springframework.security.oauth2.jwt.JwtException;
import org.springframework.security.oauth2.jwt.JwtValidators;
import org.springframework.security.oauth2.jwt.NimbusJwtDecoder;
import org.springframework.stereotype.Component;
import org.springframework.web.server.ResponseStatusException;

/** Verifies an external OIDC token before exchanging it for a workspace token. */
@Component
public class OidcIdentityVerifier {

	private final AppProperties properties;
	private JwtDecoder decoder;

	@Autowired
	public OidcIdentityVerifier(AppProperties properties) {
		this.properties = properties;
	}

	OidcIdentityVerifier(AppProperties properties, JwtDecoder decoder) {
		this.properties = properties;
		this.decoder = decoder;
	}

	@PostConstruct
	void initialize() {
		if (!properties.getOidc().isEnabled()) {
			return;
		}
		String issuer = required(properties.getOidc().getIssuerUri(), "APP_OIDC_ISSUER_URI");
		String jwkSet = required(properties.getOidc().getJwkSetUri(), "APP_OIDC_JWK_SET_URI");
		String audience = required(properties.getOidc().getAudience(), "APP_OIDC_AUDIENCE");
		NimbusJwtDecoder jwtDecoder = NimbusJwtDecoder.withJwkSetUri(jwkSet).build();
		OAuth2TokenValidator<Jwt> audienceValidator = jwt -> jwt.getAudience().contains(audience)
				? OAuth2TokenValidatorResult.success()
				: OAuth2TokenValidatorResult.failure(new OAuth2Error(
						"invalid_token", "OIDC token audience mismatch", null));
		jwtDecoder.setJwtValidator(new DelegatingOAuth2TokenValidator<>(
				JwtValidators.createDefaultWithIssuer(issuer), audienceValidator));
		this.decoder = jwtDecoder;
	}

	public ExternalIdentity verify(String token) {
		if (!properties.getOidc().isEnabled() || decoder == null) {
			throw new ResponseStatusException(HttpStatus.SERVICE_UNAVAILABLE, "OIDC 登录未启用");
		}
		try {
			Jwt jwt = decoder.decode(token);
			String subject = required(jwt.getSubject(), "OIDC subject");
			String issuer = jwt.getIssuer() == null ? "" : jwt.getIssuer().toString();
			String username = jwt.getClaimAsString(properties.getOidc().getUsernameClaim());
			if (username == null || username.isBlank()) {
				username = "user";
			}
			return new ExternalIdentity(required(issuer, "OIDC issuer"), subject, username);
		} catch (JwtException | IllegalStateException exception) {
			throw new ResponseStatusException(HttpStatus.UNAUTHORIZED, "OIDC 令牌无效或已过期");
		}
	}

	private String required(String value, String name) {
		if (value == null || value.isBlank()) {
			throw new IllegalStateException(name + " 不能为空");
		}
		return value;
	}

	public record ExternalIdentity(String issuer, String subject, String username) {
	}
}
