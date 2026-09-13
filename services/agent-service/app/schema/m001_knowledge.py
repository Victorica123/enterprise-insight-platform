"""Baseline migration copied from the established domain store; append new versions."""

from app.schema.common import ensure_column


def migrate(conn) -> None:
    conn.execute(
        """
        create table if not exists documents (
            id text primary key,
            filename text not null,
            tenant_id text not null default 'legacy',
            owner_id text not null default 'legacy',
            source_type text not null default 'document',
            external_id text not null default '',
            source_version integer not null default 1,
            payload_sha256 text not null default '',
            metadata_json text not null default '{}',
            lifecycle_status text not null default 'ACTIVE',
            supersedes_document_id text,
            superseded_by_document_id text,
            lifecycle_changed_by text,
            lifecycle_changed_at text,
            lifecycle_reason text,
            created_at text not null default current_timestamp
        )
        """
    )
    conn.execute(
        """
        create table if not exists chunks (
            id text primary key,
            document_id text not null,
            filename text not null,
            chunk_index integer not null,
            content text not null,
            tenant_id text not null default 'legacy',
            owner_id text not null default 'legacy',
            source_type text not null default 'document',
            asset_id text,
            segment_id text,
            start_ms integer,
            end_ms integer,
            speaker text,
            created_at text not null default current_timestamp,
            foreign key (document_id) references documents(id)
        )
        """
    )
    conn.execute(
        """
        create index if not exists idx_chunks_document_id
        on chunks(document_id)
        """
    )
    ensure_column(conn, table="chunks", column="embedding", definition="text")
    # A3: 真实语义 embedding（BGE 512 维），独立列 + 版本可重建；缺失时检索自动回退哈希版。
    ensure_column(conn, table="chunks", column="embedding_v2", definition="text")
    ensure_column(conn, table="chunks", column="embedding_blob", definition="blob")
    ensure_column(conn, table="chunks", column="embedding_v2_blob", definition="blob")
    ensure_column(conn, table="chunks", column="parent_key", definition="text not null default ''")
    # A4: 结构感知切块的块标题（最近的 markdown 标题）
    ensure_column(conn, table="chunks", column="chunk_title", definition="text not null default ''")
    # 统一平台来源、租户与视频时间戳字段；旧文档迁移到 legacy 隔离域。
    for column, definition in {
        "tenant_id": "text not null default 'legacy'",
        "owner_id": "text not null default 'legacy'",
        "source_type": "text not null default 'document'",
        "external_id": "text not null default ''",
        "source_version": "integer not null default 1",
        "payload_sha256": "text not null default ''",
        "metadata_json": "text not null default '{}'",
        "lifecycle_status": "text not null default 'ACTIVE'",
        "supersedes_document_id": "text",
        "superseded_by_document_id": "text",
        "lifecycle_changed_by": "text",
        "lifecycle_changed_at": "text",
        "lifecycle_reason": "text",
    }.items():
        ensure_column(conn, table="documents", column=column, definition=definition)
    for column, definition in {
        "tenant_id": "text not null default 'legacy'",
        "owner_id": "text not null default 'legacy'",
        "source_type": "text not null default 'document'",
        "asset_id": "text",
        "segment_id": "text",
        "start_ms": "integer",
        "end_ms": "integer",
        "speaker": "text",
    }.items():
        ensure_column(conn, table="chunks", column=column, definition=definition)
    conn.execute(
        """
        create unique index if not exists uk_documents_external_version
        on documents(tenant_id, source_type, external_id, source_version)
        where external_id != ''
        """
    )
    conn.execute(
        """
        create index if not exists idx_chunks_tenant_owner_source
        on chunks(tenant_id, owner_id, source_type, asset_id)
        """
    )
    conn.execute(
        """
        create table if not exists ingestion_receipts (
            event_id text primary key,
            event_type text not null,
            tenant_id text not null,
            resource_id text not null,
            resource_version integer not null,
            payload_sha256 text not null,
            document_id text not null,
            trace_id text not null,
            created_at text not null default current_timestamp,
            foreign key (document_id) references documents(id)
        )
        """
    )
    conn.execute(
        """
        create table if not exists chat_metrics (
            id integer primary key autoincrement,
            workflow_mode text not null,
            answer_mode text not null,
            retriever_mode text not null,
            intent text not null,
            complexity text not null,
            retrieval_rounds integer not null,
            query_count integer not null,
            evidence_status text not null,
            citation_status text not null,
            source_count integer not null,
            outcome text not null,
            answer_status text not null,
            latency_ms real not null,
            answer_chars integer not null,
            created_at text not null default current_timestamp
        )
        """
    )
    conn.execute(
        """
        create index if not exists idx_chat_metrics_created_at
        on chat_metrics(created_at)
        """
    )
    # V5: token 用量与成本列（老库自动迁移）
    ensure_column(conn, table="chat_metrics", column="prompt_tokens", definition="integer not null default 0")
    ensure_column(conn, table="chat_metrics", column="completion_tokens", definition="integer not null default 0")
    ensure_column(conn, table="chat_metrics", column="total_tokens", definition="integer not null default 0")
    ensure_column(conn, table="chat_metrics", column="estimated_cost_usd", definition="real not null default 0")
    ensure_column(conn, table="chat_metrics", column="tenant_id", definition="text not null default 'legacy'")
    ensure_column(conn, table="chat_metrics", column="owner_id", definition="text not null default 'legacy'")
    # 阶段 0.8 影子路由：最终执行模式、系统自选模式、是否一致（-1 = 未评估的旧记录 / 错误请求）
    ensure_column(conn, table="chat_metrics", column="execution_mode", definition="text not null default ''")
    ensure_column(conn, table="chat_metrics", column="shadow_mode", definition="text not null default ''")
    ensure_column(conn, table="chat_metrics", column="mode_agreement", definition="integer not null default -1")
    conn.execute(
        "create index if not exists idx_chat_metrics_scope on chat_metrics(tenant_id, owner_id, created_at)"
    )
    # V5: 请求日志（失败回放 + 用户反馈）；chat_metrics 保持不含问题原文
    conn.execute(
        """
        create table if not exists chat_logs (
            log_id integer primary key autoincrement,
            question text not null,
            workflow_mode text not null,
            answer_mode text not null,
            retriever_mode text not null,
            intent text not null default 'general',
            outcome text not null,
            evidence_status text not null default '',
            citation_status text not null default '',
            source_count integer not null default 0,
            latency_ms real not null default 0,
            total_tokens integer not null default 0,
            estimated_cost_usd real not null default 0,
            answer_preview text not null default '',
            trace_json text not null default '[]',
            feedback integer not null default 0,
            feedback_note text not null default '',
            created_at text not null default current_timestamp
        )
        """
    )
    conn.execute(
        """
        create index if not exists idx_chat_logs_outcome
        on chat_logs(outcome, created_at)
        """
    )
    ensure_column(conn, table="chat_logs", column="tenant_id", definition="text not null default 'legacy'")
    ensure_column(conn, table="chat_logs", column="owner_id", definition="text not null default 'legacy'")
    ensure_column(conn, table="chat_logs", column="sources_json", definition="text not null default '[]'")
    conn.execute(
        "create index if not exists idx_chat_logs_scope on chat_logs(tenant_id, owner_id, created_at)"
    )
    conn.execute(
        """
        create table if not exists system_meta (
            key text primary key,
            value integer not null default 0
        )
        """
    )
    conn.execute(
        "insert or ignore into system_meta (key, value) values ('content_revision', 0)"
    )
