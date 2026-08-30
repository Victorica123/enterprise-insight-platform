"""Chat metrics, request replay, feedback, and historical source status.

Document/chunk persistence remains in database.py. This module owns only the
observability tables' read/write behavior so feature routes do not depend on a
single all-purpose database module.
"""
from __future__ import annotations

import json
import math
import sqlite3

from app import database


def _scope_where(
    *, tenant_id: str | None = None, owner_id: str | None = None,
) -> tuple[str, list[object]]:
    clauses: list[str] = []
    params: list[object] = []
    if tenant_id is not None:
        clauses.append("tenant_id = ?")
        params.append(tenant_id)
    if owner_id is not None:
        clauses.append("owner_id = ?")
        params.append(owner_id)
    return (f"where {' and '.join(clauses)}" if clauses else ""), params


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
    tenant_id: str = "legacy",
    owner_id: str = "legacy",
) -> None:
    database.init_db()
    with database.connect() as conn:
        conn.execute(
            """
            insert into chat_metrics (
                tenant_id, owner_id, workflow_mode, answer_mode, retriever_mode, intent, complexity,
                retrieval_rounds, query_count, evidence_status, citation_status,
                source_count, outcome, answer_status, latency_ms, answer_chars,
                prompt_tokens, completion_tokens, total_tokens, estimated_cost_usd
            )
            values (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                tenant_id,
                owner_id,
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


def get_chat_metrics_summary(
    *, tenant_id: str | None = None, owner_id: str | None = None,
) -> dict[str, object]:
    database.init_db()
    where, scope_params = _scope_where(tenant_id=tenant_id, owner_id=owner_id)
    with database.connect() as conn:
        totals = conn.execute(
            f"""
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
            from chat_metrics {where}
            """,
            scope_params,
        ).fetchone()
        total = int(totals["total"] or 0)
        if total == 0:
            return empty_chat_metrics_summary()

        p95_index = max(0, math.ceil(total * 0.95) - 1)
        p95_row = conn.execute(
            f"select latency_ms from chat_metrics {where} order by latency_ms limit 1 offset ?",
            [*scope_params, p95_index],
        ).fetchone()
        feedback = conn.execute(
            f"""
            select
                sum(case when feedback > 0 then 1 else 0 end) as positive,
                sum(case when feedback < 0 then 1 else 0 end) as negative
            from chat_logs {where}{' and' if where else ' where'} feedback != 0
            """,
            scope_params,
        ).fetchone()

        def grouped_count(column: str) -> dict[str, int]:
            return {
                str(row["key"]): int(row["value"])
                for row in conn.execute(
                    f"select {column} as key, count(*) as value from chat_metrics {where} group by {column}",
                    scope_params,
                ).fetchall()
            }

        def grouped_average(key: str, value: str) -> dict[str, float]:
            return {
                str(row["key"]): round(float(row["value"] or 0), 2)
                for row in conn.execute(
                    f"select {key} as key, avg({value}) as value from chat_metrics {where} group by {key}",
                    scope_params,
                ).fetchall()
            }

        token_rows = conn.execute(
            f"select answer_mode as key, sum(total_tokens) as value from chat_metrics {where} group by answer_mode",
            scope_params,
        ).fetchall()
        cost_rows = conn.execute(
            f"select answer_mode as key, sum(estimated_cost_usd) as value from chat_metrics {where} group by answer_mode",
            scope_params,
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
    sources: list[dict[str, object]] | None = None,
    tenant_id: str = "legacy",
    owner_id: str = "legacy",
) -> int:
    database.init_db()
    with database.connect() as conn:
        cursor = conn.execute(
            """
            insert into chat_logs (
                tenant_id, owner_id, question, workflow_mode, answer_mode, retriever_mode, intent, outcome,
                evidence_status, citation_status, source_count, latency_ms,
                total_tokens, estimated_cost_usd, answer_preview, trace_json, sources_json
            )
            values (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                tenant_id,
                owner_id,
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
                json.dumps((sources or [])[:10], ensure_ascii=False),
            ),
        )
        return int(cursor.lastrowid or 0)


def list_chat_logs(
    outcome: str = "",
    limit: int = 50,
    *,
    tenant_id: str | None = None,
    owner_id: str | None = None,
) -> list[dict[str, object]]:
    database.init_db()
    clauses: list[str] = []
    params: list[object] = []
    if tenant_id is not None:
        clauses.append("tenant_id = ?")
        params.append(tenant_id)
    if owner_id is not None:
        clauses.append("owner_id = ?")
        params.append(owner_id)
    if outcome:
        clauses.append("outcome = ?")
        params.append(outcome)
    where = f" where {' and '.join(clauses)}" if clauses else ""
    params.append(max(1, min(limit, 200)))
    with database.connect() as conn:
        rows = conn.execute(
            f"select * from chat_logs{where} order by log_id desc limit ?", params
        ).fetchall()
    return [_chat_log_row_to_dict(row, include_trace=False) for row in rows]


def get_chat_log(
    log_id: int,
    *,
    tenant_id: str | None = None,
    owner_id: str | None = None,
) -> dict[str, object] | None:
    database.init_db()
    clauses = ["log_id = ?"]
    params: list[object] = [log_id]
    if tenant_id is not None:
        clauses.append("tenant_id = ?")
        params.append(tenant_id)
    if owner_id is not None:
        clauses.append("owner_id = ?")
        params.append(owner_id)
    with database.connect() as conn:
        row = conn.execute(
            f"select * from chat_logs where {' and '.join(clauses)}", params,
        ).fetchone()
    return _chat_log_row_to_dict(row, include_trace=True) if row else None


def set_chat_log_feedback(
    log_id: int,
    feedback: int,
    note: str = "",
    *,
    tenant_id: str | None = None,
    owner_id: str | None = None,
) -> bool:
    database.init_db()
    clauses = ["log_id = ?"]
    params: list[object] = [log_id]
    if tenant_id is not None:
        clauses.append("tenant_id = ?")
        params.append(tenant_id)
    if owner_id is not None:
        clauses.append("owner_id = ?")
        params.append(owner_id)
    with database.connect() as conn:
        cursor = conn.execute(
            f"update chat_logs set feedback = ?, feedback_note = ? where {' and '.join(clauses)}",
            [feedback, note[:500], *params],
        )
        return cursor.rowcount == 1


def _chat_log_row_to_dict(row: sqlite3.Row, include_trace: bool) -> dict[str, object]:
    result: dict[str, object] = {
        "log_id": int(row["log_id"]),
        "tenant_id": row["tenant_id"],
        "owner_id": row["owner_id"],
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
        try:
            sources = json.loads(row["sources_json"] or "[]") if "sources_json" in row.keys() else []
        except Exception:
            sources = []
        result["sources"] = _refresh_historical_source_lifecycle(sources)
    return result


def _refresh_historical_source_lifecycle(
    sources: list[dict[str, object]],
) -> list[dict[str, object]]:
    knowledge_document_ids = [
        str(source.get("document_id"))
        for source in sources
        if source.get("origin_type") == "approved_knowledge" and source.get("document_id")
    ]
    if not knowledge_document_ids:
        return sources
    placeholders = ",".join("?" for _ in knowledge_document_ids)
    with database.connect() as conn:
        rows = conn.execute(
            f"""
            select id, lifecycle_status, superseded_by_document_id, metadata_json
            from documents where id in ({placeholders})
            """,
            knowledge_document_ids,
        ).fetchall()
    states = {row["id"]: row for row in rows}
    refreshed: list[dict[str, object]] = []
    for source in sources:
        value = dict(source)
        row = states.get(str(value.get("document_id")))
        if row is not None:
            value["knowledge_lifecycle_status"] = row["lifecycle_status"]
            value["superseded_by_document_id"] = row["superseded_by_document_id"]
            try:
                metadata = json.loads(row["metadata_json"] or "{}")
            except Exception:
                metadata = {}
            value["knowledge_version_id"] = metadata.get("knowledge_version_id")
            value["knowledge_version_number"] = metadata.get("knowledge_version_number")
        refreshed.append(value)
    return refreshed
