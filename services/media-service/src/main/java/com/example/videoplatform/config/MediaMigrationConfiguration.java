package com.example.videoplatform.config;

import java.sql.Connection;
import java.sql.ResultSet;
import java.util.HashSet;
import java.util.Locale;
import java.util.Set;
import org.springframework.boot.autoconfigure.flyway.FlywayConfigurationCustomizer;
import org.springframework.boot.autoconfigure.flyway.FlywayMigrationStrategy;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration(proxyBeanMethods = false)
public class MediaMigrationConfiguration {
    @Bean
    FlywayConfigurationCustomizer strictMigrationHistory() {
        return configuration -> configuration.cleanDisabled(true).ignoreMigrationPatterns(new String[0]);
    }

    @Bean
    FlywayMigrationStrategy guardedMediaMigration() {
        return flyway -> {
            if (flyway.getConfiguration().isBaselineOnMigrate()) {
                try (Connection connection = flyway.getConfiguration().getDataSource().getConnection()) {
                    Set<String> tables = new HashSet<>();
                    try (ResultSet rows = connection.getMetaData().getTables(
                            connection.getCatalog(), connection.getSchema(), "%", new String[]{"TABLE"})) {
                        while (rows.next()) tables.add(rows.getString("TABLE_NAME").toLowerCase(Locale.ROOT));
                    }
                    if (!tables.isEmpty() && !tables.contains("flyway_schema_history")) {
                        if (!"1".equals(flyway.getConfiguration().getBaselineVersion().getVersion())) {
                            throw new IllegalStateException("Legacy Media baseline must be version 1");
                        }
                        LegacyMediaSchema.verify(flyway.getConfiguration().getDataSource());
                    }
                } catch (java.sql.SQLException exception) {
                    throw new IllegalStateException("Unable to verify legacy Media schema", exception);
                }
            }
            flyway.migrate();
        };
    }
}
