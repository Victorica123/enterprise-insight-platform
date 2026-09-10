package com.example.videoplatform.workflow;

import com.example.videoplatform.config.AppProperties;
import java.util.Set;
import java.util.stream.Collectors;
import org.springframework.core.env.Environment;
import org.springframework.stereotype.Component;

/** Tenant-level policy gate before transcript or summary payloads leave the platform. */
@Component
public class ModelEgressPolicy {

	private final AppProperties properties;
	private final Environment environment;

	public ModelEgressPolicy(AppProperties properties, Environment environment) {
		this.properties = properties;
		this.environment = environment;
	}

	public void requireTranscriptAllowed(String tenantId) {
		if (properties.getTranscript().isEnabled()) {
			requireAllowed(tenantId);
		}
	}

	public void requireSummaryAllowed(String tenantId) {
		if (properties.getSummary().isEnabled()) {
			requireAllowed(tenantId);
		}
	}

	public boolean isAllowed(String tenantId) {
		Set<String> allowed = properties.getModelEgress().getAllowedTenants().stream()
				.map(String::trim).filter(value -> !value.isBlank()).collect(Collectors.toSet());
		boolean production = java.util.Arrays.stream(environment.getActiveProfiles())
				.anyMatch(profile -> profile.equalsIgnoreCase("production") || profile.equalsIgnoreCase("prod"))
				|| "production".equalsIgnoreCase(environment.getProperty("APP_ENV", ""));
		if (production) {
			return tenantId != null && allowed.contains(tenantId);
		}
		String policy = properties.getModelEgress().getPolicy();
		if ("allow".equalsIgnoreCase(policy)) {
			return true;
		}
		return "allowlist".equalsIgnoreCase(policy) && tenantId != null && allowed.contains(tenantId);
	}

	private void requireAllowed(String tenantId) {
		if (!isAllowed(tenantId)) {
			throw new ModelEgressDeniedException(
					"External model data egress is not approved for tenant " + tenantId);
		}
	}
}
