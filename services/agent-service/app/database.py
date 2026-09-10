import json
import sqlite3
import os
from contextlib import contextmanager
from pathlib import Path
from typing import Iterable, Iterator

from app.db_compat import MySqlConnectionCompat, connect_mysql
from app.embeddings import build_embedding, embed_real, embedding_to_json


DB_PATH = Path(os.getenv(
    "AGENT_DATABASE_PATH",
    str(Path(__file__).resolve().parents[1] / "data" / "knowledge_base.sqlite3"),
))

_INITIALIZED_DB_PATH: str | Path | None = None


def mysql_database_url() -> str:
    return os.getenv("AGENT_DATABASE_URL", "").strip()


def uses_mysql() -> bool:
    return mysql_database_url().lower().startswith(("mysql://", "mysql+pymysql://"))


def database_identity() -> str:
    """Stable cache/migration identity without including database credentials."""
    if uses_mysql():
        from urllib.parse import urlparse

        parsed = urlparse(mysql_database_url())
        return f"mysql://{parsed.hostname}:{parsed.port or 3306}/{parsed.path.lstrip('/')}"
    return str(DB_PATH.resolve())


def initialization_marker_is_current(marker: str | Path | None) -> bool:
    identity = database_identity()
    if str(marker) != identity:
        return False
    return uses_mysql() or DB_PATH.exists()


def prepare_database_storage() -> None:
    if not uses_mysql():
        DB_PATH.parent.mkdir(parents=True, exist_ok=True)


def validate_database_configuration() -> None:
    if (
        os.getenv("APP_ENV", "development").strip().lower() == "production"
        and os.getenv("AGENT_REQUIRE_MYSQL", "0").strip().lower() in {"1", "true", "yes", "on"}
        and not uses_mysql()
    ):
        raise RuntimeError(
            "Production pilot requires AGENT_DATABASE_URL=mysql://... when "
            "AGENT_REQUIRE_MYSQL is enabled."
        )


def init_db() -> None:
    """建库建表；按 DB_PATH 记忆化，避免每个请求重复执行 DDL（测试改路径自动失效）。"""
    global _INITIALIZED_DB_PATH
    validate_database_configuration()
    current_path = database_identity()
    if initialization_marker_is_current(_INITIALIZED_DB_PATH):
        return
    prepare_database_storage()
    with connect() as conn:
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
    _INITIALIZED_DB_PATH = current_path


@contextmanager
def connect() -> Iterator[sqlite3.Connection | MySqlConnectionCompat]:
    """Yields a connection that is committed (or rolled back) and CLOSED on exit.

    相比裸 sqlite3.connect 的上下文用法（只 commit 不 close，句柄泄漏到 GC）：
    - busy_timeout 5s：多 worker 并发下等锁而不是立刻 database is locked；
    - WAL：读写互不阻塞（同一进程内 begin immediate 语义不变）；
    - 退出时真正 close，Windows 上 WAL 的 -wal/-shm 文件才能被删除/替换。
    只读文件系统等场景下 WAL pragma 失败不影响读写，忽略即可。
    """
    if uses_mysql():
        conn = connect_mysql(mysql_database_url())
        try:
            yield conn
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()
        return

    conn = sqlite3.connect(DB_PATH, timeout=5.0)
    conn.row_factory = sqlite3.Row
    conn.execute("pragma busy_timeout = 5000")
    conn.execute("pragma foreign_keys = on")
    try:
        conn.execute("pragma journal_mode = wal")
    except sqlite3.OperationalError:
        pass
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def ensure_column(conn: sqlite3.Connection, table: str, column: str, definition: str) -> None:
    columns = conn.execute(f"pragma table_info({table})").fetchall()
    if any(row["name"] == column for row in columns):
        return

    try:
        conn.execute(f"alter table {table} add column {column} {definition}")
    except sqlite3.OperationalError:
        # Two request threads/processes may both observe an old schema before
        # SQLite serializes ALTER TABLE. If the winner committed the same
        # column while this statement waited, the migration is already done.
        refreshed = conn.execute(f"pragma table_info({table})").fetchall()
        if any(row["name"] == column for row in refreshed):
            return
        raise


def insert_document(
    document_id: str,
    filename: str,
    chunks: Iterable[tuple[str, str]],
    *,
    conn: sqlite3.Connection | None = None,
    tenant_id: str = "legacy",
    owner_id: str = "legacy",
    source_type: str = "document",
    external_id: str = "",
    source_version: int = 1,
    payload_sha256: str = "",
    metadata: dict[str, object] | None = None,
    chunk_metadata: list[dict[str, object]] | None = None,
) -> int:
    """chunks: (块标题, 内容) 迭代；chunk_index 由写入顺序生成。"""
    chunk_rows = list(chunks)
    # A3: 真实 embedding 批量生成（模型不可用时为 None，只写哈希版）。
    real_vectors = embed_real([content for _title, content in chunk_rows])
    rows_to_insert = []
    if chunk_metadata is not None and len(chunk_metadata) != len(chunk_rows):
        raise ValueError("chunk_metadata length must match chunks length")
    for index, (title, content) in enumerate(chunk_rows):
        details = chunk_metadata[index] if chunk_metadata else {}
        rows_to_insert.append(
            (
                f"{document_id}:{details.get('segment_id') or index}",
                document_id,
                filename,
                index,
                content,
                embedding_to_json(build_embedding(content)),
                embedding_to_json(real_vectors[index]) if real_vectors else None,
                title,
                tenant_id,
                owner_id,
                source_type,
                details.get("asset_id"),
                details.get("segment_id"),
                details.get("start_ms"),
                details.get("end_ms"),
                details.get("speaker"),
            )
        )

    if conn is not None:
        _insert_document_rows(
            conn,
            document_id,
            filename,
            rows_to_insert,
            tenant_id=tenant_id,
            owner_id=owner_id,
            source_type=source_type,
            external_id=external_id,
            source_version=source_version,
            payload_sha256=payload_sha256,
            metadata=metadata,
        )
    else:
        init_db()
        with connect() as local_conn:
            _insert_document_rows(
                local_conn,
                document_id,
                filename,
                rows_to_insert,
                tenant_id=tenant_id,
                owner_id=owner_id,
                source_type=source_type,
                external_id=external_id,
                source_version=source_version,
                payload_sha256=payload_sha256,
                metadata=metadata,
            )

    return len(chunk_rows)


def _insert_document_rows(
    conn: sqlite3.Connection,
    document_id: str,
    filename: str,
    rows: list[tuple[object, ...]],
    *,
    tenant_id: str,
    owner_id: str,
    source_type: str,
    external_id: str,
    source_version: int,
    payload_sha256: str,
    metadata: dict[str, object] | None,
) -> None:
    conn.execute(
        """
        insert into documents (
            id, filename, tenant_id, owner_id, source_type, external_id,
            source_version, payload_sha256, metadata_json
        ) values (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            document_id,
            filename,
            tenant_id,
            owner_id,
            source_type,
            external_id,
            source_version,
            payload_sha256,
            json.dumps(metadata or {}, ensure_ascii=False, sort_keys=True),
        ),
    )
    conn.executemany(
        """
        insert into chunks (
            id, document_id, filename, chunk_index, content, embedding, embedding_v2, chunk_title,
            tenant_id, owner_id, source_type, asset_id, segment_id, start_ms, end_ms, speaker
        ) values (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        rows,
    )
    bump_content_revision(conn)


def list_document_rows(
    *,
    tenant_id: str | None = None,
    owner_id: str | None = None,
) -> list[sqlite3.Row]:
    init_db()
    predicates: list[str] = []
    parameters: list[object] = []
    if tenant_id is not None:
        predicates.append("documents.tenant_id = ?")
        parameters.append(tenant_id)
    if owner_id is not None:
        predicates.append("documents.owner_id = ?")
        parameters.append(owner_id)
    where_clause = f"where {' and '.join(predicates)}" if predicates else ""
    with connect() as conn:
        return conn.execute(
            f"""
            select
                documents.id,
                documents.filename,
                documents.source_type,
                documents.external_id,
                documents.lifecycle_status,
                documents.created_at,
                count(chunks.id) as chunk_count
            from documents
            left join chunks on chunks.document_id = documents.id
            {where_clause}
            group by documents.id
            order by documents.created_at desc
            """,
            parameters,
        ).fetchall()


def list_chunk_rows(
    *,
    tenant_id: str | None = None,
    owner_id: str | None = None,
    asset_ids: tuple[str, ...] = (),
) -> list[sqlite3.Row]:
    init_db()
    predicates: list[str] = ["documents.lifecycle_status = 'ACTIVE'"]
    parameters: list[object] = []
    if tenant_id is not None:
        predicates.append("chunks.tenant_id = ?")
        parameters.append(tenant_id)
    if owner_id is not None:
        predicates.append("chunks.owner_id = ?")
        parameters.append(owner_id)
    if asset_ids:
        placeholders = ",".join("?" for _ in asset_ids)
        # Asset selection narrows video evidence only. Uploaded documents and
        # governed knowledge remain available inside the already-authorized
        # workspace scope, matching the UI and product retrieval contract.
        predicates.append(
            f"(chunks.source_type != 'video' or chunks.asset_id in ({placeholders}))"
        )
        parameters.extend(asset_ids)
    where_clause = f"where {' and '.join(predicates)}" if predicates else ""
    with connect() as conn:
        return conn.execute(
            f"""
            select chunks.document_id, chunks.filename, chunks.chunk_index, chunks.content,
                   chunks.embedding, chunks.embedding_v2, chunks.chunk_title,
                   chunks.tenant_id, chunks.owner_id, chunks.source_type, chunks.asset_id,
                   chunks.segment_id, chunks.start_ms, chunks.end_ms, chunks.speaker,
                   documents.external_id, documents.payload_sha256, documents.metadata_json,
                   documents.lifecycle_status, documents.supersedes_document_id,
                   documents.superseded_by_document_id
            from chunks
            join documents on documents.id = chunks.document_id
            {where_clause}
            order by chunks.created_at asc, chunks.chunk_index asc
            """,
            parameters,
        ).fetchall()


def get_ingestion_receipt(event_id: str, *, conn: sqlite3.Connection) -> sqlite3.Row | None:
    return conn.execute(
        "select * from ingestion_receipts where event_id = ?",
        (event_id,),
    ).fetchone()


def find_evidence_document(
    tenant_id: str,
    source_type: str,
    external_id: str,
    source_version: int,
    *,
    conn: sqlite3.Connection,
) -> sqlite3.Row | None:
    return conn.execute(
        """
        select * from documents
        where tenant_id = ? and source_type = ? and external_id = ? and source_version = ?
        """,
        (tenant_id, source_type, external_id, source_version),
    ).fetchone()


def insert_ingestion_receipt(
    *,
    event_id: str,
    event_type: str,
    tenant_id: str,
    resource_id: str,
    resource_version: int,
    payload_sha256: str,
    document_id: str,
    trace_id: str,
    conn: sqlite3.Connection,
) -> None:
    conn.execute(
        """
        insert into ingestion_receipts (
            event_id, event_type, tenant_id, resource_id, resource_version,
            payload_sha256, document_id, trace_id
        ) values (?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            event_id,
            event_type,
            tenant_id,
            resource_id,
            resource_version,
            payload_sha256,
            document_id,
            trace_id,
        ),
    )


def delete_document(
    document_id: str,
    *,
    tenant_id: str | None = None,
    owner_id: str | None = None,
) -> bool:
    init_db()
    predicates = ["id = ?"]
    parameters: list[object] = [document_id]
    if tenant_id is not None:
        predicates.append("tenant_id = ?")
        parameters.append(tenant_id)
    if owner_id is not None:
        predicates.append("owner_id = ?")
        parameters.append(owner_id)
    with connect() as conn:
        existing = conn.execute(
            f"select id, source_type from documents where {' and '.join(predicates)}",
            parameters,
        ).fetchone()
        if existing is None:
            return False
        if existing["source_type"] == "knowledge":
            return False

        conn.execute("delete from chunks where document_id = ?", (document_id,))
        conn.execute("delete from documents where id = ?", (document_id,))
        bump_content_revision(conn)
        return True


def get_embedding_stats() -> dict[str, int]:
    init_db()
    with connect() as conn:
        row = conn.execute(
            """
            select
                count(*) as total_chunks,
                sum(case when embedding is not null and length(embedding) > 0 then 1 else 0 end) as embedded_chunks,
                sum(case when embedding_v2 is not null and length(embedding_v2) > 0 then 1 else 0 end) as embedded_chunks_v2
            from chunks
            """
        ).fetchone()

    total_chunks = int(row["total_chunks"] or 0)
    embedded_chunks = int(row["embedded_chunks"] or 0)
    embedded_chunks_v2 = int(row["embedded_chunks_v2"] or 0)
    return {
        "total_chunks": total_chunks,
        "embedded_chunks": embedded_chunks,
        "missing_chunks": max(0, total_chunks - embedded_chunks),
        # A3: 真实 embedding 覆盖（模型不可用时为 0，检索自动回退哈希版）
        "embedded_chunks_v2": embedded_chunks_v2,
        "missing_chunks_v2": max(0, total_chunks - embedded_chunks_v2),
    }


def rebuild_chunk_embeddings() -> dict[str, int]:
    """Rebuild deterministic vectors without destroying a good v2 fallback.

    Real-model inference is intentionally batched.  If a batch cannot be
    embedded (offline model download, transient inference failure, etc.), the
    existing ``embedding_v2`` value is preserved and retrieval can continue to
    use the previously indexed semantic vector.
    """
    init_db()
    updated_count = 0
    batch_size = max(1, _read_positive_int_env("EMBEDDING_REBUILD_BATCH_SIZE", 64))
    with connect() as conn:
        rows = conn.execute("select id, content from chunks order by id").fetchall()
        for start in range(0, len(rows), batch_size):
            batch = rows[start : start + batch_size]
            real_vectors = embed_real([row["content"] for row in batch])
            for index, row in enumerate(batch):
                conn.execute(
                    "update chunks set embedding = ? where id = ?",
                    (embedding_to_json(build_embedding(row["content"])), row["id"]),
                )
                if real_vectors is not None:
                    conn.execute(
                        "update chunks set embedding_v2 = ? where id = ?",
                        (embedding_to_json(real_vectors[index]), row["id"]),
                    )
                updated_count += 1
        if updated_count:
            bump_content_revision(conn)

    stats = get_embedding_stats()
    return {
        **stats,
        "updated_chunks": updated_count,
    }


def _read_positive_int_env(name: str, default: int) -> int:
    try:
        return max(1, int(os.getenv(name, str(default))))
    except ValueError:
        return default


def get_content_revision() -> int:
    init_db()
    with connect() as conn:
        row = conn.execute(
            "select value from system_meta where key = 'content_revision'"
        ).fetchone()
    return int(row["value"] if row else 0)


def bump_content_revision(conn: sqlite3.Connection) -> None:
    conn.execute(
        """
        insert into system_meta (key, value) values ('content_revision', 1)
        on conflict(key) do update set value = value + 1
        """
    )
