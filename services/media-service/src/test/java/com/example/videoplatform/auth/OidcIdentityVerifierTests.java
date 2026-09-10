package com.example.videoplatform.auth;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;
import static org.mockito.Mockito.mock;
import static org.mockito.Mockito.when;

import com.example.videoplatform.config.AppProperties;
import java.time.Instant;
import org.junit.jupiter.api.Test;
import org.springframework.security.oauth2.jwt.BadJwtException;
import org.springframework.security.oauth2.jwt.Jwt;
import org.springframework.security.oauth2.jwt.JwtDecoder;
import org.springframework.web.server.ResponseStatusException;

class OidcIdentityVerifierTests {

	@Test
	void derivesStableExternalIdentityOnlyAfterDecoderVerification() {
		AppProperties properties = enabledProperties();
		JwtDecoder decoder = mock(JwtDecoder.class);
		when(decoder.decode("external-token")).thenReturn(Jwt.withTokenValue("external-token")
				.header("alg", "RS256")
				.subject("subject-1")
				.issuer("http://identity/realms/enterprise-insight")
				.claim("preferred_username", "alice")
				.issuedAt(Instant.now()).expiresAt(Instant.now().plusSeconds(60)).build());

		var identity = new OidcIdentityVerifier(properties, decoder).verify("external-token");

		assertThat(identity.subject()).isEqualTo("subject-1");
		assertThat(identity.username()).isEqualTo("alice");
		assertThat(identity.issuer()).contains("enterprise-insight");
	}

	@Test
	void mapsDecoderFailureToUnauthorizedWithoutProviderDetails() {
		JwtDecoder decoder = mock(JwtDecoder.class);
		when(decoder.decode("bad")).thenThrow(new BadJwtException("sensitive provider detail"));
		assertThatThrownBy(() -> new OidcIdentityVerifier(enabledProperties(), decoder).verify("bad"))
				.isInstanceOf(ResponseStatusException.class)
				.hasMessageContaining("401");
	}

	private AppProperties enabledProperties() {
		AppProperties properties = new AppProperties();
		properties.getOidc().setEnabled(true);
		properties.getOidc().setUsernameClaim("preferred_username");
		return properties;
	}
}
