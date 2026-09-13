package com.example.videoplatform.config;

import static org.assertj.core.api.Assertions.assertThat;
import org.junit.jupiter.api.Test;
import org.springframework.boot.test.context.runner.ApplicationContextRunner;

class DomainPropertiesTests {
    @Test
    void legacyPrefixesBindToTheSameDomainBeansExposedByFacade() {
        new ApplicationContextRunner().withUserConfiguration(AppConfiguration.class)
                .withPropertyValues("app.quota.max-active-tasks-per-user=7", "app.workflow.task-lease-duration=12s",
                        "app.jwt.issuer=issuer-fixture", "app.storage.s3.bucket=bucket-fixture",
                        "app.integration.agent.max-attempts=4", "app.model-egress.allowed-tenants=team-a,team-b")
                .run(context -> {
                    AppProperties facade = context.getBean(AppProperties.class);
                    assertThat(facade.getQuota()).isSameAs(context.getBean(QuotaProperties.class));
                    assertThat(facade.getQuota().getMaxActiveTasksPerUser()).isEqualTo(7);
                    assertThat(facade.getWorkflow().getTaskLeaseDuration().toSeconds()).isEqualTo(12);
                    assertThat(facade.getJwt().getIssuer()).isEqualTo("issuer-fixture");
                    assertThat(facade.getStorage().getS3().getBucket()).isEqualTo("bucket-fixture");
                    assertThat(facade.getIntegration().getAgent().getMaxAttempts()).isEqualTo(4);
                    assertThat(facade.getModelEgress().getAllowedTenants()).containsExactly("team-a", "team-b");
                });
    }
}
