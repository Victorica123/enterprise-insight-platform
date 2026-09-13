package com.example.videoplatform.workflow;

import java.util.UUID;

/** Explicit per-execution observer; no thread-local context or external I/O inside log transactions. */
public final class TaskStageObserver {
    private final TaskStageLogService logs;
    private final String taskId;
    private final String runId = UUID.randomUUID().toString();

    public TaskStageObserver(TaskStageLogService logs, String taskId) {
        this.logs = logs;
        this.taskId = taskId;
    }

    public static TaskStageObserver untracked() { return new TaskStageObserver(null, null); }

    public <T> T run(TaskStageLog.Stage stage, Action<T> action) {
        long id = logs == null ? 0 : logs.begin(taskId, runId, stage);
        try {
            T result = action.get();
            if (logs != null) logs.finish(id, TaskStageLog.Outcome.SUCCEEDED, null);
            return result;
        } catch (Exception exception) {
            if (logs != null) logs.finish(id, TaskStageLog.Outcome.FAILED, TaskStageLog.ErrorCode.STAGE_FAILED);
            if (exception instanceof RuntimeException runtime) throw runtime;
            throw new IllegalStateException("Media stage failed: " + stage, exception);
        }
    }

    @FunctionalInterface
    public interface Action<T> { T get() throws Exception; }
}
