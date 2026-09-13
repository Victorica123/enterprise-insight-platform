package com.example.videoplatform.workflow;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;

import com.example.videoplatform.config.RetentionProperties;
import java.time.Instant;
import java.util.UUID;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.jdbc.core.JdbcTemplate;

@SpringBootTest
class TaskStageLogIntegrationTests {
    @Autowired private TaskStageLogService logs;
    @Autowired private RetentionProperties retention;
    @Autowired private JdbcTemplate jdbc;

    @Test
    void recordsOnlyExecutedStagesAndNeverCopiesSensitiveExceptions() {
        String taskId = UUID.randomUUID().toString();
        TaskStageObserver observer = new TaskStageObserver(logs, taskId);
        observer.run(TaskStageLog.Stage.STORAGE_RESOLVE, () -> "resolved");
        assertThatThrownBy(() -> observer.run(TaskStageLog.Stage.TRANSCRIPTION,
                () -> { throw new IllegalStateException("secret-api-key /private/storage/recording.wav"); }))
                .isInstanceOf(IllegalStateException.class);
        var page = logs.list(taskId, 0, 50);
        assertThat(page.items()).extracting(TaskStageLog.View::stage).containsExactly("STORAGE_RESOLVE", "TRANSCRIPTION");
        assertThat(page.items()).extracting(TaskStageLog.View::status).containsExactly("SUCCEEDED", "FAILED");
        assertThat(page.items().get(1).errorCode()).isEqualTo("STAGE_FAILED");
        assertThat(page.toString()).doesNotContain("secret-api-key", "/private/storage/");
    }

    @Test
    void pagingIsBoundedAndRecoveryPreventsLateSuccess() {
        String taskId = UUID.randomUUID().toString();
        long first = logs.begin(taskId, UUID.randomUUID().toString(), TaskStageLog.Stage.TRANSCRIPTION);
        long second = logs.begin(taskId, UUID.randomUUID().toString(), TaskStageLog.Stage.SUMMARY);
        var page = logs.list(taskId, 0, 1);
        assertThat(page.hasMore()).isTrue();
        assertThat(page.nextCursor()).isEqualTo(first);
        assertThat(logs.list(taskId, page.nextCursor(), 1).items().get(0).id()).isEqualTo(second);
        logs.abandonProcessing(taskId);
        assertThat(logs.finish(first, TaskStageLog.Outcome.SUCCEEDED, null)).isFalse();
        assertThat(logs.list(taskId, 0, 50).items()).allMatch(item -> item.status().equals("ABANDONED"));
        assertThatThrownBy(() -> logs.list(taskId, 0, 101)).isInstanceOf(IllegalArgumentException.class);
    }

    @Test
    void auditRetentionUsesExistingPolicyAndBoundedBatches() {
        String taskId = UUID.randomUUID().toString();
        long old = logs.begin(taskId, UUID.randomUUID().toString(), TaskStageLog.Stage.SUMMARY);
        long recent = logs.begin(taskId, UUID.randomUUID().toString(), TaskStageLog.Stage.SUMMARY);
        jdbc.update("update task_stage_log set started_at=? where id=?", Instant.now().minusSeconds(400L * 86400), old);
        boolean enabled = retention.isEnabled();
        try {
            retention.setEnabled(true);
            assertThat(logs.enforceRetention()).isPositive();
            assertThat(logs.list(taskId, 0, 50).items()).extracting(TaskStageLog.View::id).containsExactly(recent);
        } finally {
            retention.setEnabled(enabled);
        }
    }
}
