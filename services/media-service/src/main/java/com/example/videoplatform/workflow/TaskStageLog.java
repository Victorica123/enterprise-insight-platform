package com.example.videoplatform.workflow;

import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.GeneratedValue;
import jakarta.persistence.GenerationType;
import jakarta.persistence.Id;
import jakarta.persistence.Index;
import jakarta.persistence.Table;
import java.time.Instant;

@Entity
@Table(name = "task_stage_log", indexes = {
        @Index(name = "idx_task_stage_cursor", columnList = "taskId,id"),
        @Index(name = "idx_task_stage_retention", columnList = "startedAt,id")})
public class TaskStageLog {
    @Id @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;
    @Column(nullable = false)
    private String taskId;
    @Column(nullable = false, length = 36)
    private String runId;
    @Column(nullable = false, length = 32)
    private String stage;
    @Column(nullable = false, length = 16)
    private String status;
    @Column(nullable = false)
    private Instant startedAt;
    private Instant finishedAt;
    private Long durationMs;
    @Column(length = 32)
    private String errorCode;

    protected TaskStageLog() { }

    TaskStageLog(String taskId, String runId, Stage stage, Instant now) {
        this.taskId = taskId;
        this.runId = runId;
        this.stage = stage.name();
        this.status = "RUNNING";
        this.startedAt = now;
    }

    public Long getId() { return id; }
    public Instant getStartedAt() { return startedAt; }
    public View view() { return new View(id, runId, stage, status, startedAt, finishedAt, durationMs, errorCode); }

    public enum Stage { STORAGE_RESOLVE, AUDIO_EXTRACTION, TRANSCRIPTION, SUMMARY, RESULT_REUSE, RESULT_COMMIT, DELIVERY }
    public enum Outcome { SUCCEEDED, FAILED, ABANDONED }
    public enum ErrorCode { STAGE_FAILED, LEASE_RECOVERED, DELIVERY_REJECTED, DELIVERY_RETRY, LEASE_LOST }
    public record View(long id, String runId, String stage, String status, Instant startedAt,
                       Instant finishedAt, Long durationMs, String errorCode) { }
}
