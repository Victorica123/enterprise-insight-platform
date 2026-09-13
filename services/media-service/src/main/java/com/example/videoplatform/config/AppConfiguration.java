package com.example.videoplatform.config;

import org.springframework.boot.context.properties.EnableConfigurationProperties;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration(proxyBeanMethods = false)
@EnableConfigurationProperties({JwtProperties.class, OidcProperties.class, StorageProperties.class, WorkflowProperties.class, QuotaProperties.class, MqProperties.class, TranscriptProperties.class, SummaryProperties.class, SecurityProperties.class, IntegrationProperties.class, ModelEgressProperties.class, RetentionProperties.class})
public class AppConfiguration {
	@Bean
	AppProperties appProperties(JwtProperties jwt,
			OidcProperties oidc,
			StorageProperties storage,
			WorkflowProperties workflow,
			QuotaProperties quota,
			MqProperties mq,
			TranscriptProperties transcript,
			SummaryProperties summary,
			SecurityProperties security,
			IntegrationProperties integration,
			ModelEgressProperties modelEgress,
			RetentionProperties retention) {
		return new AppProperties(jwt, oidc, storage, workflow, quota, mq, transcript, summary, security, integration, modelEgress, retention);
	}
}
