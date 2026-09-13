package com.example.videoplatform.workflow;

import com.example.videoplatform.config.RetentionProperties;
import java.time.Duration;
import java.time.Instant;
import java.time.temporal.ChronoUnit;
import java.util.List;
import org.springframework.data.domain.PageRequest;
import org.springframework.scheduling.annotation.Scheduled;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Propagation;
import org.springframework.transaction.annotation.Transactional;

@Service
public class TaskStageLogService {
    private final TaskStageLogRepository repository;
    private final RetentionProperties retention;

    public TaskStageLogService(TaskStageLogRepository repository, RetentionProperties retention) {
        this.repository = repository;
        this.retention = retention;
    }

    @Transactional(propagation = Propagation.REQUIRES_NEW)
    public long begin(String taskId, String runId, TaskStageLog.Stage stage) {
        return repository.save(new TaskStageLog(taskId, runId, stage, Instant.now())).getId();
    }

    @Transactional(propagation = Propagation.REQUIRES_NEW)
    public boolean finish(long id, TaskStageLog.Outcome outcome, TaskStageLog.ErrorCode error) {
        TaskStageLog row = repository.findById(id).orElse(null);
        if (row == null) return false;
        Instant now = Instant.now();
        return repository.finishRunning(id, outcome.name(), now,
                Math.max(0, Duration.between(row.getStartedAt(), now).toMillis()),
                error == null ? null : error.name()) == 1;
    }

    @Transactional
    public void abandonProcessing(String taskId) {
        repository.abandonProcessing(taskId, Instant.now());
    }

    /** The caller must authorize the owning task before reading its log. */
    @Transactional(readOnly = true)
    public Page list(String taskId, long after, int limit) {
        if (after < 0 || limit < 1 || limit > 100) throw new IllegalArgumentException("阶段日志分页参数无效");
        List<TaskStageLog> rows = repository.findByTaskIdAndIdGreaterThanOrderByIdAsc(
                taskId, after, PageRequest.of(0, limit + 1));
        List<TaskStageLog.View> items = rows.stream().limit(limit).map(TaskStageLog::view).toList();
        return new Page(items, items.isEmpty() ? after : items.get(items.size() - 1).id(), rows.size() > limit);
    }

    @Scheduled(fixedDelayString = "${app.retention.scan-interval-ms:3600000}",
            initialDelayString = "${app.retention.initial-delay-ms:60000}")
    @Transactional
    public int enforceRetention() {
        if (!retention.isEnabled()) return 0;
        if (retention.getAuditDays() <= 0) throw new IllegalStateException("Audit retention days must be positive");
        List<TaskStageLog> expired = repository.findByStartedAtBeforeOrderByIdAsc(
                Instant.now().minus(retention.getAuditDays(), ChronoUnit.DAYS),
                PageRequest.of(0, Math.max(1, Math.min(1000, retention.getBatchSize()))));
        repository.deleteAllInBatch(expired);
        return expired.size();
    }

    public record Page(List<TaskStageLog.View> items, long nextCursor, boolean hasMore) { }
}
