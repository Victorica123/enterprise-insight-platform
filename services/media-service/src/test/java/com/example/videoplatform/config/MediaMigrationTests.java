package com.example.videoplatform.config;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;

import com.example.videoplatform.auth.UserAccount;
import com.example.videoplatform.auth.Workspace;
import com.example.videoplatform.auth.WorkspaceInvitation;
import com.example.videoplatform.auth.WorkspaceMember;
import com.example.videoplatform.integration.IntegrationEventOutbox;
import com.example.videoplatform.workflow.MediaAsset;
import com.example.videoplatform.workflow.MediaCleanupJob;
import com.example.videoplatform.workflow.VideoTask;
import com.example.videoplatform.workflow.WorkflowDispatchOutbox;
import java.sql.Types;
import java.util.UUID;
import org.flywaydb.core.Flyway;
import org.hibernate.boot.MetadataSources;
import org.hibernate.boot.model.naming.CamelCaseToUnderscoresNamingStrategy;
import org.hibernate.boot.registry.StandardServiceRegistryBuilder;
import org.junit.jupiter.api.Test;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.jdbc.datasource.DriverManagerDataSource;

class MediaMigrationTests {
    private final DriverManagerDataSource dataSource = new DriverManagerDataSource(
            "jdbc:h2:mem:migration-" + UUID.randomUUID() + ";DB_CLOSE_DELAY=-1", "sa", "");
    private final JdbcTemplate jdbc = new JdbcTemplate(dataSource);
    private final MediaMigrationConfiguration configuration = new MediaMigrationConfiguration();

    private Flyway flyway(boolean baseline) {
        var config = Flyway.configure().dataSource(dataSource).locations("classpath:db/migration/h2")
                .baselineOnMigrate(baseline).baselineVersion("1");
        configuration.strictMigrationHistory().customize(config);
        return config.load();
    }

    @Test
    void vendorEnumMetadataPreservesCompatibilityWithoutAcceptingTruncatedText() {
        var expected = new LegacyMediaSchema.Column(Types.OTHER, "enum('failed', 'processing', 'ready', 'retention_expired')", 17, 0);
        assertThat(LegacyMediaSchema.compatible(expected,
                new LegacyMediaSchema.Column(Types.CHAR, "enum", 17, 0))).isTrue();
        assertThat(LegacyMediaSchema.compatible(expected,
                new LegacyMediaSchema.Column(Types.VARCHAR, "varchar", 255, 0))).isTrue();
        assertThat(LegacyMediaSchema.compatible(expected,
                new LegacyMediaSchema.Column(Types.VARCHAR, "varchar", 5, 0))).isFalse();
        assertThat(LegacyMediaSchema.compatible(expected,
                new LegacyMediaSchema.Column(Types.CHAR, "enum", 17, 1))).isFalse();
    }

    @Test
    void emptyDatabaseMigratesAndRepeatedStartupPreservesRows() {
        Flyway flyway = flyway(false);
        configuration.guardedMediaMigration().migrate(flyway);
        jdbc.update("insert into user_account(user_id, username) values ('owner', 'existing-user')");
        configuration.guardedMediaMigration().migrate(flyway);
        assertThat(flyway.info().current().getVersion().getVersion()).isEqualTo("2");
        assertThat(jdbc.queryForObject("select username from user_account where user_id='owner'", String.class))
                .isEqualTo("existing-user");
        assertThatThrownBy(flyway::clean).hasMessageContaining("cleanDisabled");
    }

    @Test
    void legacyHibernateDatabaseNeedsOptInAndKeepsIdentityAndTasks() {
        createLegacy();
        jdbc.update("insert into user_account(user_id, username, password_hash) values ('owner', 'alice', 'retained-hash')");
        jdbc.update("insert into video_task(task_id, tenant_id, owner, transcript_version, transcript) values ('task', 'tenant', 'owner', 1, 'retained-evidence')");
        assertThatThrownBy(() -> configuration.guardedMediaMigration().migrate(flyway(false)))
                .hasMessageContaining("non-empty");
        configuration.guardedMediaMigration().migrate(flyway(true));
        assertThat(jdbc.queryForObject("select transcript from video_task where task_id='task'", String.class))
                .isEqualTo("retained-evidence");
        assertThat(jdbc.queryForObject("select password_hash from user_account where user_id='owner'", String.class))
                .isEqualTo("retained-hash");
        assertThat(flyway(false).info().current().getVersion().getVersion()).isEqualTo("2");
    }

    @Test
    void wrongLegacyColumnsOrMissingUniqueConstraintCannotBeBaselined() {
        createLegacy();
        jdbc.execute("alter table user_account drop column password_hash");
        assertThatThrownBy(() -> configuration.guardedMediaMigration().migrate(flyway(true)))
                .hasMessageContaining("password_hash");
        assertNoHistory();
        jdbc.execute("alter table user_account add password_hash varchar(255)");
        jdbc.execute("alter table user_account drop constraint uk_user_account_username");
        assertThatThrownBy(() -> configuration.guardedMediaMigration().migrate(flyway(true)))
                .hasMessageContaining("unique constraint missing");
        assertNoHistory();
    }

    @Test
    void unknownNonemptyDatabaseIsNotAdopted() {
        jdbc.execute("create table unrelated_business(id integer primary key)");
        jdbc.update("insert into unrelated_business values (17)");
        assertThatThrownBy(() -> configuration.guardedMediaMigration().migrate(flyway(true)))
                .hasMessageContaining("unknown tables");
        assertNoHistory();
        assertThat(jdbc.queryForObject("select id from unrelated_business", Integer.class)).isEqualTo(17);
    }

    @Test
    void futureHistoryAndChecksumChangesFailClosed() {
        Flyway flyway = flyway(false);
        configuration.guardedMediaMigration().migrate(flyway);
        jdbc.update("update \"flyway_schema_history\" set \"version\"='999' where \"version\"='2'");
        assertThatThrownBy(() -> configuration.guardedMediaMigration().migrate(flyway))
                .hasMessageContaining("not resolved locally");
        jdbc.update("update \"flyway_schema_history\" set \"version\"='2' where \"version\"='999'");
        jdbc.update("update \"flyway_schema_history\" set \"checksum\"=123 where \"version\"='1'");
        assertThatThrownBy(() -> configuration.guardedMediaMigration().migrate(flyway))
                .hasMessageContaining("checksum mismatch");
    }

    private void assertNoHistory() {
        assertThat(jdbc.queryForObject("select count(*) from information_schema.tables where lower(table_name)='flyway_schema_history'", Integer.class))
                .isZero();
    }

    private void createLegacy() {
        var registry = new StandardServiceRegistryBuilder()
                .applySetting("hibernate.connection.datasource", dataSource)
                .applySetting("hibernate.hbm2ddl.auto", "create")
                .applySetting("hibernate.physical_naming_strategy", CamelCaseToUnderscoresNamingStrategy.class).build();
        try {
            var metadata = new MetadataSources(registry);
            for (Class<?> entity : new Class<?>[]{UserAccount.class, Workspace.class, WorkspaceInvitation.class,
                    WorkspaceMember.class, VideoTask.class, MediaAsset.class, MediaCleanupJob.class,
                    WorkflowDispatchOutbox.class, IntegrationEventOutbox.class}) metadata.addAnnotatedClass(entity);
            try (var ignored = metadata.buildMetadata().buildSessionFactory()) { /* schema-only legacy fixture */ }
        } finally {
            StandardServiceRegistryBuilder.destroy(registry);
        }
    }
}
