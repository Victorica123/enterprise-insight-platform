package com.example.videoplatform.workflow;

import static org.assertj.core.api.Assertions.assertThat;

import com.example.videoplatform.config.AppProperties;
import java.util.List;
import org.junit.jupiter.api.Test;
import org.springframework.mock.env.MockEnvironment;

class ModelEgressPolicyTests {

	@Test
	void productionAllowsOnlyExplicitTenant() {
		AppProperties properties = new AppProperties();
		properties.getModelEgress().setPolicy("allow");
		properties.getModelEgress().setAllowedTenants(List.of("tenant-a"));
		MockEnvironment environment = new MockEnvironment().withProperty("APP_ENV", "production");
		ModelEgressPolicy policy = new ModelEgressPolicy(properties, environment);

		assertThat(policy.isAllowed("tenant-a")).isTrue();
		assertThat(policy.isAllowed("tenant-b")).isFalse();
	}

	@Test
	void developmentRetainsExplicitLocalAllowMode() {
		AppProperties properties = new AppProperties();
		properties.getModelEgress().setPolicy("allow");
		ModelEgressPolicy policy = new ModelEgressPolicy(properties, new MockEnvironment());
		assertThat(policy.isAllowed("local-demo")).isTrue();
	}
}
