package com.example.videoplatform.config;

import org.springframework.boot.context.properties.ConfigurationProperties;

@ConfigurationProperties(prefix = "app.oidc")
public class OidcProperties extends FeatureProperties {
	private String issuerUri;
	private String jwkSetUri;
	private String audience = "enterprise-insight-web";
	private String usernameClaim = "preferred_username";

	public String getIssuerUri() {
		return issuerUri;
	}

	public void setIssuerUri(String issuerUri) {
		this.issuerUri = issuerUri;
	}

	public String getJwkSetUri() {
		return jwkSetUri;
	}

	public void setJwkSetUri(String jwkSetUri) {
		this.jwkSetUri = jwkSetUri;
	}

	public String getAudience() {
		return audience;
	}

	public void setAudience(String audience) {
		this.audience = audience;
	}

	public String getUsernameClaim() {
		return usernameClaim;
	}

	public void setUsernameClaim(String usernameClaim) {
		this.usernameClaim = usernameClaim;
	}
}
