CREATE TABLE task_stage_log (
    id BIGINT AUTO_INCREMENT PRIMARY KEY,
    task_id VARCHAR(255) NOT NULL, run_id VARCHAR(36) NOT NULL,
    stage VARCHAR(32) NOT NULL, status VARCHAR(16) NOT NULL,
    started_at DATETIME(6) NOT NULL, finished_at DATETIME(6), duration_ms BIGINT, error_code VARCHAR(32)
);
CREATE INDEX idx_task_stage_cursor ON task_stage_log (task_id, id);
CREATE INDEX idx_task_stage_retention ON task_stage_log (started_at, id);
