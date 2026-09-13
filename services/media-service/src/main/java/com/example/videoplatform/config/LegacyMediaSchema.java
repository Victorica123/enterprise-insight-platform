package com.example.videoplatform.config;

import java.sql.Connection;
import java.sql.DriverManager;
import java.sql.ResultSet;
import java.sql.SQLException;
import java.sql.Types;
import java.util.HashMap;
import java.util.HashSet;
import java.util.Locale;
import java.util.Map;
import java.util.Set;
import java.util.UUID;
import javax.sql.DataSource;
import org.springframework.core.io.ClassPathResource;
import org.springframework.jdbc.datasource.init.ScriptUtils;

/** Read-only legacy validation against the immutable V1 SQL, independent of evolving JPA mappings. */
final class LegacyMediaSchema {
    private LegacyMediaSchema() { }

    static void verify(DataSource source) {
        // The reference is a private, transient H2 schema. Closing its only connection destroys it.
        try (Connection reference = DriverManager.getConnection("jdbc:h2:mem:legacy-check-" + UUID.randomUUID(), "sa", "");
             Connection actual = source.getConnection()) {
            ScriptUtils.executeSqlScript(reference, new ClassPathResource("db/migration/h2/V1__legacy_media_schema.sql"));
            Map<String, String> expectedTables = tables(reference);
            Map<String, String> actualTables = tables(actual);
            Set<String> unknown = new HashSet<>(actualTables.keySet());
            unknown.removeAll(expectedTables.keySet());
            unknown.remove("media_asset"); // Retained historical table from the original tenant migration.
            if (!unknown.isEmpty()) throw new IllegalStateException("Legacy Media contains unknown tables: " + unknown);
            for (var table : expectedTables.entrySet()) {
                String actualName = actualTables.get(table.getKey());
                if (actualName == null) throw new IllegalStateException("Legacy Media missing table: " + table.getKey());
                Map<String, Column> expectedColumns = columns(reference, table.getValue());
                Map<String, Column> actualColumns = columns(actual, actualName);
                for (var column : expectedColumns.entrySet()) {
                    if (!compatible(column.getValue(), actualColumns.get(column.getKey()))) {
                        throw new IllegalStateException("Legacy Media column mismatch: " + table.getKey() + "." + column.getKey());
                    }
                }
                if (!primaryKey(reference, table.getValue()).equals(primaryKey(actual, actualName))) {
                    throw new IllegalStateException("Legacy Media primary key mismatch: " + table.getKey());
                }
                if (!uniqueKeys(actual, actualName).containsAll(uniqueKeys(reference, table.getValue()))) {
                    throw new IllegalStateException("Legacy Media unique constraint missing: " + table.getKey());
                }
            }
        } catch (SQLException exception) {
            throw new IllegalStateException("Unable to verify legacy Media schema", exception);
        }
    }

    private static Map<String, String> tables(Connection connection) throws SQLException {
        Map<String, String> result = new HashMap<>();
        try (ResultSet rows = connection.getMetaData().getTables(connection.getCatalog(), connection.getSchema(), "%", new String[]{"TABLE"})) {
            while (rows.next()) result.put(normalize(rows.getString("TABLE_NAME")), rows.getString("TABLE_NAME"));
        }
        return result;
    }

    private static Map<String, Column> columns(Connection connection, String table) throws SQLException {
        Map<String, Column> result = new HashMap<>();
        try (ResultSet rows = connection.getMetaData().getColumns(connection.getCatalog(), connection.getSchema(), table, "%")) {
            while (rows.next()) result.put(normalize(rows.getString("COLUMN_NAME")), new Column(
                    rows.getInt("DATA_TYPE"), normalize(rows.getString("TYPE_NAME")), rows.getInt("COLUMN_SIZE"), rows.getInt("NULLABLE")));
        }
        return result;
    }

    static boolean compatible(Column expected, Column actual) {
        if (actual == null || expected.nullable == 0 && actual.nullable != 0) return false;
        // H2 includes the labels in TYPE_NAME; Connector/J reports only ENUM.
        if (enumType(expected)) return enumType(actual) || text(actual) && actual.size >= expected.size;
        if (expected.type == Types.TIMESTAMP_WITH_TIMEZONE || expected.type == Types.TIMESTAMP) {
            return actual.type == Types.TIMESTAMP_WITH_TIMEZONE || actual.type == Types.TIMESTAMP;
        }
        if (text(expected)) {
            // H2 TEXT is a large VARCHAR; MySQL TEXT reports LONGVARCHAR and a 65535-byte limit.
            int required = Math.min(expected.size, 65535);
            return text(actual) && actual.size >= required;
        }
        return expected.type == actual.type;
    }

    private static boolean enumType(Column column) {
        return column.name.equals("enum") || column.name.startsWith("enum(");
    }

    private static boolean text(Column column) {
        return column.type == Types.VARCHAR || column.type == Types.CHAR || column.type == Types.LONGVARCHAR || column.type == Types.CLOB;
    }

    private static Set<String> primaryKey(Connection connection, String table) throws SQLException {
        Set<String> result = new HashSet<>();
        try (ResultSet rows = connection.getMetaData().getPrimaryKeys(connection.getCatalog(), connection.getSchema(), table)) {
            while (rows.next()) result.add(normalize(rows.getString("COLUMN_NAME")));
        }
        return result;
    }

    private static Set<Set<String>> uniqueKeys(Connection connection, String table) throws SQLException {
        Map<String, Set<String>> indexes = new HashMap<>();
        try (ResultSet rows = connection.getMetaData().getIndexInfo(connection.getCatalog(), connection.getSchema(), table, true, false)) {
            while (rows.next()) {
                String column = rows.getString("COLUMN_NAME");
                if (column != null) indexes.computeIfAbsent(rows.getString("INDEX_NAME"), key -> new HashSet<>()).add(normalize(column));
            }
        }
        return new HashSet<>(indexes.values());
    }

    private static String normalize(String value) { return value.toLowerCase(Locale.ROOT); }
    record Column(int type, String name, int size, int nullable) { }
}
