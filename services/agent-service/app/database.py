import json
import sqlite3
import math
from contextlib import contextmanager
from pathlib import Path
from typing import Iterable, Iterator

from app.embeddings import build_embedding, embed_real, embedding_to_json


DB_PATH = Path(__file__).resolve().parents[1] / "data" / "knowledge_base.sqlite3"

_INITIALIZED_DB_PATH: Path | None = None


def init_db() -> None:
    """建库建表；按 DB_PATH 记忆化，避免每个请求重复执行 DDL（测试改路径自动失效）。"""
    global _INITIALIZED_DB_PATH
    current_path = DB_PATH.resolve()
    if _INITIALIZED_DB_PATH == current_path and current_path.exists():
        return
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    with connect() as conn:
        conn.execute(
            """
            create table if not exists documents (
                id text primary key,
                filename text not null,
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
def connect() -> Iterator[sqlite3.Connection]:
    """Yields a connection that is committed (or rolled back) and CLOSED on exit.

    相比裸 sqlite3.connect 的上下文用法（只 commit 不 close，句柄泄漏到 GC）：
    - busy_timeout 5s：多 worker 并发下等锁而不是立刻 database is locked；
    - WAL：读写互不阻塞（同一进程内 begin immediate 语义不变）；
    - 退出时真正 close，Windows 上 WAL 的 -wal/-shm 文件才能被删除/替换。
    只读文件系统等场景下 WAL pragma 失败不影响读写，忽略即可。
    """
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

    conn.execute(f"alter table {table} add column {column} {definition}")


def insert_document(
    document_id: str,
    filename: str,
    chunks: Iterable[tuple[str, str]],
    *,
    conn: sqlite3.Connection | None = None,
) -> int:
    """chunks: (块标题, 内容) 迭代；chunk_index 由写入顺序生成。"""
    chunk_rows = list(chunks)
    # A3: 真实 embedding 批量生成（模型不可用时为 None，只写哈希版）。
    real_vectors = embed_real([content for _title, content in chunk_rows])
    rows_to_insert = []
    for index, (title, content) in enumerate(chunk_rows):
        rows_to_insert.append(
            (
                f"{document_id}:{index}",
                document_id,
                filename,
                index,
                content,
                embedding_to_json(build_embedding(content)),
                embedding_to_json(real_vectors[index]) if real_vectors else None,
                title,
            )
        )

    if conn is not None:
        _insert_document_rows(conn, document_id, filename, rows_to_insert)
    else:
        init_db()
        with connect() as local_conn:
            _insert_document_rows(local_conn, document_id, filename, rows_to_insert)

    return len(chunk_rows)


def _insert_document_rows(
    conn: sqlite3.Connection,
    document_id: str,
    filename: str,
    rows: list[tuple[object, ...]],
) -> None:
    conn.execute(
        "insert into documents (id, filename) values (?, ?)",
        (document_id, filename),
    )
    conn.executemany(
        """
        insert into chunks (id, document_id, filename, chunk_index, content, embedding, embedding_v2, chunk_title)
        values (?, ?, ?, ?, ?, ?, ?, ?)
        """,
        rows,
    )
    bump_content_revision(conn)


def list_document_rows() -> list[sqlite3.Row]:
    init_db()
    with connect() as conn:
        return conn.execute(
            """
            select
                documents.id,
                documents.filename,
                documents.created_at,
                count(chunks.id) as chunk_count
            from documents
            left join chunks on chunks.document_id = documents.id
            group by documents.id
            order by documents.created_at desc
            """
        ).fetchall()


def list_chunk_rows() -> list[sqlite3.Row]:
    init_db()
    with connect() as conn:
        return conn.execute(
            """
            select document_id, filename, chunk_index, content, embedding, embedding_v2, chunk_title
            from chunks
            order by created_at asc, chunk_index asc
            """
        ).fetchall()


def delete_document(document_id: str) -> bool:
    init_db()
    with connect() as conn:
        existing = conn.execute(
            "select id from documents where id = ?",
            (document_id,),
        ).fetchone()
        if existing is None:
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
    init_db()
    updated_count = 0
    with connect() as conn:
        rows = conn.execute("select id, content from chunks").fetchall()
        real_vectors = embed_real([row["content"] for row in rows])
        for index, row in enumerate(rows):
            conn.execute(
                "update chunks set embedding = ?, embedding_v2 = ? where id = ?",
                (
                    embedding_to_json(build_embedding(row["content"])),
                    embedding_to_json(real_vectors[index]) if real_vectors else None,
                    row["id"],
                ),
            )
            updated_count += 1
        if updated_count:
            bump_content_revision(conn)

    stats = get_embedding_stats()
    return {
        **stats,
        "updated_chunks": updated_count,
    }


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


def record_chat_metric(
    *,
    workflow_mode: str,
    answer_mode: str,
    retriever_mode: str,
    intent: str,
    complexity: str,
    retrieval_rounds: int,
    query_count: int,
    evidence_status: str,
    citation_status: str,
    source_count: int,
    outcome: str,
    answer_status: str,
    latency_ms: float,
    answer_chars: int,
    prompt_tokens: int = 0,
    completion_tokens: int = 0,
    total_tokens: int = 0,
    estimated_cost_usd: float = 0.0,
) -> None:
    init_db()
    with connect() as conn:
        conn.execute(
            """
            insert into chat_metrics (
                workflow_mode, answer_mode, retriever_mode, intent, complexity,
                retrieval_rounds, query_count, evidence_status, citation_status,
                source_count, outcome, answer_status, latency_ms, answer_chars,
                prompt_tokens, completion_tokens, total_tokens, estimated_cost_usd
            )
            values (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                workflow_mode,
                answer_mode,
                retriever_mode,
                intent,
                complexity,
                retrieval_rounds,
                query_count,
                evidence_status,
                citation_status,
                source_count,
                outcome,
                answer_status,
                latency_ms,
                answer_chars,
                prompt_tokens,
                completion_tokens,
                total_tokens,
                round(estimated_cost_usd, 6),
            ),
        )


def get_chat_metrics_summary() -> dict[str, object]:
    init_db()
    with connect() as conn:
        totals = conn.execute(
            """
            select
                count(*) as total,
                sum(case when outcome = 'answered' then 1 else 0 end) as answered,
                sum(case when outcome = 'refused' then 1 else 0 end) as refused,
                sum(case when outcome = 'error' then 1 else 0 end) as errors,
                sum(case when evidence_status = 'passed' then 1 else 0 end) as evidence_passed,
                sum(case when outcome = 'answered' and workflow_mode = 'agentic' then 1 else 0 end)
                    as citation_eligible,
                sum(case when outcome = 'answered' and workflow_mode = 'agentic'
                    and citation_status in ('passed', 'repaired') then 1 else 0 end) as citation_ready,
                avg(latency_ms) as avg_latency_ms,
                avg(retrieval_rounds) as avg_retrieval_rounds,
                avg(query_count) as avg_query_count,
                avg(source_count) as avg_source_count,
                sum(prompt_tokens) as prompt_tokens,
                sum(completion_tokens) as completion_tokens,
                sum(total_tokens) as total_tokens,
                sum(estimated_cost_usd) as total_cost
            from chat_metrics
            """
        ).fetchone()
        total = int(totals["total"] or 0)
        if total == 0:
            return empty_chat_metrics_summary()

        p95_index = max(0, math.ceil(total * 0.95) - 1)
        p95_row = conn.execute(
            "select latency_ms from chat_metrics order by latency_ms limit 1 offset ?",
            (p95_index,),
        ).fetchone()
        feedback = conn.execute(
            """
            select
                sum(case when feedback > 0 then 1 else 0 end) as positive,
                sum(case when feedback < 0 then 1 else 0 end) as negative
            from chat_logs where feedback != 0
            """
        ).fetchone()

        def grouped_count(column: str) -> dict[str, int]:
            return {
                str(row["key"]): int(row["value"])
                for row in conn.execute(
                    f"select {column} as key, count(*) as value from chat_metrics group by {column}"
                ).fetchall()
            }

        def grouped_average(key: str, value: str) -> dict[str, float]:
            return {
                str(row["key"]): round(float(row["value"] or 0), 2)
                for row in conn.execute(
                    f"select {key} as key, avg({value}) as value from chat_metrics group by {key}"
                ).fetchall()
            }

        token_rows = conn.execute(
            "select answer_mode as key, sum(total_tokens) as value from chat_metrics group by answer_mode"
        ).fetchall()
        cost_rows = conn.execute(
            "select answer_mode as key, sum(estimated_cost_usd) as value from chat_metrics group by answer_mode"
        ).fetchall()
        workflow_usage = grouped_count("workflow_mode")
        answer_mode_usage = grouped_count("answer_mode")
        retriever_usage = grouped_count("retriever_mode")
        intent_usage = grouped_count("intent")
        avg_latency_by_workflow = grouped_average("workflow_mode", "latency_ms")
        avg_latency_by_answer_mode = grouped_average("answer_mode", "latency_ms")

    answered = int(totals["answered"] or 0)
    refused = int(totals["refused"] or 0)
    errors = int(totals["errors"] or 0)
    evidence_passed = int(totals["evidence_passed"] or 0)
    citation_eligible = int(totals["citation_eligible"] or 0)
    citation_ready = int(totals["citation_ready"] or 0)
    total_prompt_tokens = int(totals["prompt_tokens"] or 0)
    total_completion_tokens = int(totals["completion_tokens"] or 0)
    total_tokens = int(totals["total_tokens"] or 0)
    total_cost = float(totals["total_cost"] or 0)
    positive_feedback = int(feedback["positive"] or 0)
    negative_feedback = int(feedback["negative"] or 0)
    feedback_count = positive_feedback + negative_feedback

    return {
        "total_requests": total,
        "answered_requests": answered,
        "refused_requests": refused,
        "error_requests": errors,
        "answer_rate": answered / total,
        "refusal_rate": refused / total,
        "error_rate": errors / total,
        "evidence_pass_rate": evidence_passed / total,
        "citation_ready_rate": citation_ready / citation_eligible if citation_eligible else 1.0,
        "avg_latency_ms": round(float(totals["avg_latency_ms"] or 0), 2),
        "p95_latency_ms": round(float(p95_row["latency_ms"] if p95_row else 0), 2),
        "avg_retrieval_rounds": round(float(totals["avg_retrieval_rounds"] or 0), 2),
        "avg_query_count": round(float(totals["avg_query_count"] or 0), 2),
        "avg_source_count": round(float(totals["avg_source_count"] or 0), 2),
        "workflow_usage": workflow_usage,
        "answer_mode_usage": answer_mode_usage,
        "retriever_usage": retriever_usage,
        "intent_usage": intent_usage,
        "avg_latency_by_workflow": avg_latency_by_workflow,
        "avg_latency_by_answer_mode": avg_latency_by_answer_mode,
        "total_prompt_tokens": total_prompt_tokens,
        "total_completion_tokens": total_completion_tokens,
        "total_tokens": total_tokens,
        "avg_tokens_per_request": round(total_tokens / total, 2),
        "total_estimated_cost_usd": round(total_cost, 6),
        "avg_cost_per_request_usd": round(total_cost / total, 6),
        "tokens_by_answer_mode": {str(row["key"]): int(row["value"] or 0) for row in token_rows},
        "cost_by_answer_mode": {
            str(row["key"]): round(float(row["value"] or 0), 6) for row in cost_rows
        },
        "feedback_count": feedback_count,
        "positive_feedback": positive_feedback,
        "negative_feedback": negative_feedback,
        "satisfaction_rate": positive_feedback / feedback_count if feedback_count else 1.0,
    }


def empty_chat_metrics_summary() -> dict[str, object]:
    return {
        "total_requests": 0,
        "answered_requests": 0,
        "refused_requests": 0,
        "error_requests": 0,
        "answer_rate": 0.0,
        "refusal_rate": 0.0,
        "error_rate": 0.0,
        "evidence_pass_rate": 0.0,
        "citation_ready_rate": 0.0,
        "avg_latency_ms": 0.0,
        "p95_latency_ms": 0.0,
        "avg_retrieval_rounds": 0.0,
        "avg_query_count": 0.0,
        "avg_source_count": 0.0,
        "workflow_usage": {},
        "answer_mode_usage": {},
        "retriever_usage": {},
        "intent_usage": {},
        "avg_latency_by_workflow": {},
        "avg_latency_by_answer_mode": {},
        "total_prompt_tokens": 0,
        "total_completion_tokens": 0,
        "total_tokens": 0,
        "avg_tokens_per_request": 0.0,
        "total_estimated_cost_usd": 0.0,
        "avg_cost_per_request_usd": 0.0,
        "tokens_by_answer_mode": {},
        "cost_by_answer_mode": {},
        "feedback_count": 0,
        "positive_feedback": 0,
        "negative_feedback": 0,
        "satisfaction_rate": 1.0,
    }


# ---------------------------------------------------------------------------
# V5: 请求日志（失败回放 + 用户反馈）
# ---------------------------------------------------------------------------

def record_chat_log(
    *,
    question: str,
    workflow_mode: str,
    answer_mode: str,
    retriever_mode: str,
    intent: str,
    outcome: str,
    evidence_status: str,
    citation_status: str,
    source_count: int,
    latency_ms: float,
    total_tokens: int,
    estimated_cost_usd: float,
    answer_preview: str,
    trace: list[dict[str, str]],
) -> int:
    init_db()
    with connect() as conn:
        cursor = conn.execute(
            """
            insert into chat_logs (
                question, workflow_mode, answer_mode, retriever_mode, intent, outcome,
                evidence_status, citation_status, source_count, latency_ms,
                total_tokens, estimated_cost_usd, answer_preview, trace_json
            )
            values (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                question[:300],
                workflow_mode,
                answer_mode,
                retriever_mode,
                intent,
                outcome,
                evidence_status,
                citation_status,
                source_count,
                round(latency_ms, 2),
                total_tokens,
                round(estimated_cost_usd, 6),
                answer_preview[:400],
                json.dumps(trace[:40], ensure_ascii=False),
            ),
        )
        return int(cursor.lastrowid or 0)


def list_chat_logs(outcome: str = "", limit: int = 50) -> list[dict[str, object]]:
    init_db()
    clauses = ""
    params: list[object] = []
    if outcome:
        clauses = " where outcome = ?"
        params.append(outcome)
    params.append(max(1, min(limit, 200)))
    with connect() as conn:
        rows = conn.execute(
            f"select * from chat_logs{clauses} order by log_id desc limit ?", params
        ).fetchall()
    return [_chat_log_row_to_dict(row, include_trace=False) for row in rows]


def get_chat_log(log_id: int) -> dict[str, object] | None:
    init_db()
    with connect() as conn:
        row = conn.execute("select * from chat_logs where log_id = ?", (log_id,)).fetchone()
    return _chat_log_row_to_dict(row, include_trace=True) if row else None


def set_chat_log_feedback(log_id: int, feedback: int, note: str = "") -> bool:
    init_db()
    with connect() as conn:
        cursor = conn.execute(
            "update chat_logs set feedback = ?, feedback_note = ? where log_id = ?",
            (feedback, note[:500], log_id),
        )
        return cursor.rowcount == 1


def _chat_log_row_to_dict(row: sqlite3.Row, include_trace: bool) -> dict[str, object]:
    result: dict[str, object] = {
        "log_id": int(row["log_id"]),
        "question": row["question"],
        "workflow_mode": row["workflow_mode"],
        "answer_mode": row["answer_mode"],
        "retriever_mode": row["retriever_mode"],
        "intent": row["intent"],
        "outcome": row["outcome"],
        "evidence_status": row["evidence_status"],
        "citation_status": row["citation_status"],
        "source_count": int(row["source_count"]),
        "latency_ms": float(row["latency_ms"]),
        "total_tokens": int(row["total_tokens"]),
        "estimated_cost_usd": float(row["estimated_cost_usd"]),
        "answer_preview": row["answer_preview"],
        "feedback": int(row["feedback"]),
        "feedback_note": row["feedback_note"],
        "created_at": row["created_at"],
    }
    if include_trace:
        try:
            result["trace"] = json.loads(row["trace_json"] or "[]")
        except Exception:
            result["trace"] = []
    return result
