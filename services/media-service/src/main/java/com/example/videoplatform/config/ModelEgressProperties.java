package com.example.videoplatform.config;

import java.util.ArrayList;
import java.util.List;
import org.springframework.boot.context.properties.ConfigurationProperties;

@ConfigurationProperties(prefix = "app.model-egress")
public class ModelEgressProperties {
	private String policy = "allow";
	private List<String> allowedTenants = new ArrayList<>();

	public String getPolicy() {
		return policy;
	}

	public void setPolicy(String policy) {
		this.policy = policy;
	}

	public List<String> getAllowedTenants() {
		return allowedTenants;
	}

	public void setAllowedTenants(List<String> allowedTenants) {
		this.allowedTenants = allowedTenants == null ? new ArrayList<>() : new ArrayList<>(allowedTenants);
	}
}
