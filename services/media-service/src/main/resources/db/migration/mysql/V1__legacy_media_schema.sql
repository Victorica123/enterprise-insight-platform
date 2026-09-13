-- Initial schema matching the pre-Flyway Media Service. Append new versions; never edit an applied migration.
CREATE TABLE user_account (
    user_id VARCHAR(255) NOT NULL PRIMARY KEY,
    username VARCHAR(50) NOT NULL,
    password_hash VARCHAR(255), identity_issuer VARCHAR(255), identity_subject VARCHAR(255), primary_tenant_id VARCHAR(64),
    CONSTRAINT uk_user_account_username UNIQUE (username),
    CONSTRAINT uk_user_account_oidc_identity UNIQUE (identity_issuer, identity_subject)
);
CREATE TABLE workspace (
    tenant_id VARCHAR(255) NOT NULL PRIMARY KEY, name VARCHAR(100) NOT NULL, created_by VARCHAR(64) NOT NULL,
    workspace_type ENUM('PERSONAL','TEAM'), created_at DATETIME(6) NOT NULL
);
CREATE TABLE workspace_member (
    member_id VARCHAR(255) NOT NULL PRIMARY KEY, tenant_id VARCHAR(64) NOT NULL, user_id VARCHAR(64) NOT NULL,
    role ENUM('ADMIN','MEMBER','OWNER','VIEWER') NOT NULL, joined_at DATETIME(6) NOT NULL,
    CONSTRAINT uk_workspace_member_tenant_user UNIQUE (tenant_id, user_id)
);
CREATE TABLE workspace_invitation (
    invitation_id VARCHAR(255) NOT NULL PRIMARY KEY, tenant_id VARCHAR(64) NOT NULL, code_hash VARCHAR(64) NOT NULL,
    created_by VARCHAR(64) NOT NULL, created_at DATETIME(6) NOT NULL, expires_at DATETIME(6) NOT NULL,
    accepted_by VARCHAR(64), accepted_at DATETIME(6),
    CONSTRAINT uk_workspace_invitation_code_hash UNIQUE (code_hash)
);
CREATE TABLE video_task (
    task_id VARCHAR(255) NOT NULL PRIMARY KEY, video_id VARCHAR(255), owner VARCHAR(255), tenant_id VARCHAR(255),
    trace_id VARCHAR(255), file_name VARCHAR(255), storage_path VARCHAR(255), content_md5 VARCHAR(255),
    processing_lease_id VARCHAR(255), processing_lease_expires_at DATETIME(6),
    transcript TEXT, transcript_segments_json TEXT, transcript_language VARCHAR(255), transcript_duration_ms BIGINT,
    transcript_version INTEGER NOT NULL, summary TEXT, status ENUM('COMPLETED','FAILED','QUEUED','SUMMARIZING','TRANSCRIBING'), error_message TEXT,
    created_at DATETIME(6), updated_at DATETIME(6)
);
CREATE INDEX idx_video_task_owner_created ON video_task (owner, created_at);
CREATE INDEX idx_video_task_tenant_owner_created ON video_task (tenant_id, owner, created_at);
CREATE INDEX idx_video_task_status_updated ON video_task (status, updated_at);
CREATE INDEX idx_video_task_content_md5 ON video_task (content_md5);
CREATE INDEX idx_video_task_lease ON video_task (status, processing_lease_expires_at);
CREATE TABLE media_asset_scoped (
    asset_key VARCHAR(128) NOT NULL PRIMARY KEY, tenant_id VARCHAR(128) NOT NULL, content_md5 VARCHAR(64) NOT NULL,
    status ENUM('FAILED','PROCESSING','READY','RETENTION_EXPIRED'), storage_path VARCHAR(255), transcript TEXT, transcript_segments_json TEXT,
    transcript_language VARCHAR(255), transcript_duration_ms BIGINT, summary TEXT, error_message TEXT,
    created_at DATETIME(6), updated_at DATETIME(6),
    CONSTRAINT uk_media_asset_tenant_md5 UNIQUE (tenant_id, content_md5)
);
CREATE INDEX idx_media_asset_scope_status ON media_asset_scoped (tenant_id, status);
CREATE INDEX idx_media_asset_scope_md5 ON media_asset_scoped (tenant_id, content_md5);
CREATE TABLE media_cleanup_job (
    job_id VARCHAR(255) NOT NULL PRIMARY KEY, storage_path VARCHAR(512) NOT NULL, attempt_count INTEGER NOT NULL,
    last_error TEXT, next_attempt_at DATETIME(6), created_at DATETIME(6), updated_at DATETIME(6)
);
CREATE TABLE workflow_dispatch_outbox (
    task_id VARCHAR(64) NOT NULL PRIMARY KEY, status ENUM('CLAIMED','PENDING','SENT') NOT NULL, attempts INTEGER NOT NULL,
    next_attempt_at DATETIME(6) NOT NULL, last_error TEXT, created_at DATETIME(6) NOT NULL, dispatched_at DATETIME(6),
    claim_id VARCHAR(64), claim_expires_at DATETIME(6)
);
CREATE INDEX idx_workflow_dispatch_pending ON workflow_dispatch_outbox (status, next_attempt_at);
CREATE INDEX idx_workflow_dispatch_claim ON workflow_dispatch_outbox (status, claim_expires_at);
CREATE TABLE integration_event_outbox (
    event_id VARCHAR(255) NOT NULL PRIMARY KEY, event_type VARCHAR(100) NOT NULL, aggregate_id VARCHAR(64) NOT NULL,
    payload TEXT NOT NULL, status ENUM('CLAIMED','DEAD','PENDING','SENT') NOT NULL, attempts INTEGER NOT NULL, next_attempt_at DATETIME(6) NOT NULL,
    last_error TEXT, created_at DATETIME(6) NOT NULL, published_at DATETIME(6), claim_id VARCHAR(64), claim_expires_at DATETIME(6)
);
CREATE INDEX idx_outbox_status_next_attempt ON integration_event_outbox (status, next_attempt_at);
CREATE INDEX idx_outbox_claim_expiry ON integration_event_outbox (status, claim_expires_at);
