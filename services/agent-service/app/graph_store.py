"""V4 GraphRAG persistence: rule-based entity/relation extraction into SQLite.

学习版图谱：不依赖 Neo4j，用 SQLite 两张表存实体和关系，
抽取规则针对企业交付类文档（客户/项目/负责人/合同/日期/延期原因/风险条款）。
节点契约独立，后续可平滑迁移到 Neo4j + LLM 抽取。
"""
from __future__ import annotations

import json
import sqlite3
import uuid
from datetime import UTC, datetime
from time import perf_counter

from app import database
from app.graph_algorithms import MAX_PATH_DEPTH as MAX_PATH_DEPTH
from app.graph_algorithms import MAX_PATHS as MAX_PATHS
from app.graph_algorithms import GraphPathStep as GraphPathStep
from app.graph_algorithms import find_relation_paths, relation_neighborhood
from app.graph_extraction import (
    GraphEntity,
    GraphRelation,
    extract_graph_from_text,
    normalize_name,
)


def init_graph_store() -> None:
    database.init_db()








def _now() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds")


def _persist(
    entities: list[GraphEntity],
    relations: list[GraphRelation],
    *,
    conn: sqlite3.Connection | None = None,
    tenant_id: str = "legacy",
    owner_id: str = "legacy",
) -> None:
    if not entities and not relations:
        return
    if conn is not None:
        _persist_rows(conn, entities, relations, tenant_id=tenant_id, owner_id=owner_id)
        return
    with database.connect() as local_conn:
        _persist_rows(local_conn, entities, relations, tenant_id=tenant_id, owner_id=owner_id)


def _persist_rows(
    conn: sqlite3.Connection,
    entities: list[GraphEntity],
    relations: list[GraphRelation],
    *,
    tenant_id: str,
    owner_id: str,
) -> None:
    now = _now()
    for entity in entities:
        row = conn.execute(
            """
            select entity_id, mention_count, document_ids from graph_entities
            where tenant_id = ? and owner_id = ? and name = ? and entity_type = ?
            """,
            (tenant_id, owner_id, entity.name, entity.entity_type),
        ).fetchone()
        if row is None:
            conn.execute(
                """
                insert into graph_entities (
                    entity_id, tenant_id, owner_id, name, entity_type,
                    mention_count, document_ids, created_at
                ) values (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    str(uuid.uuid4()),
                    tenant_id,
                    owner_id,
                    entity.name,
                    entity.entity_type,
                    entity.mention_count,
                    json.dumps(entity.document_ids, ensure_ascii=False),
                    now,
                ),
            )
        else:
            documents = set(json.loads(row["document_ids"] or "[]"))
            documents.update(entity.document_ids)
            conn.execute(
                "update graph_entities set mention_count = mention_count + ?, document_ids = ? where entity_id = ?",
                (entity.mention_count, json.dumps(sorted(documents), ensure_ascii=False), row["entity_id"]),
            )
    for relation in relations:
        conn.execute(
            """
            insert or ignore into graph_relations (
                relation_id, tenant_id, owner_id, source_name, source_type, relation_type,
                target_name, target_type, evidence, document_id, filename, chunk_index, created_at
            ) values (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                str(uuid.uuid4()),
                tenant_id,
                owner_id,
                relation.source_name,
                relation.source_type,
                relation.relation_type,
                relation.target_name,
                relation.target_type,
                relation.evidence,
                relation.document_id,
                relation.filename,
                relation.chunk_index,
                now,
            ),
        )


def index_document_graph(
    document_id: str,
    *,
    conn: sqlite3.Connection | None = None,
) -> dict[str, int]:
    """上传后增量抽取一个文档的实体关系。"""
    init_graph_store()
    if conn is not None:
        return _index_document_graph_rows(conn, document_id)
    with database.connect() as local_conn:
        return _index_document_graph_rows(local_conn, document_id)


def _index_document_graph_rows(conn: sqlite3.Connection, document_id: str) -> dict[str, int]:
    rows = conn.execute(
        """
        select chunks.document_id, chunks.filename, chunks.chunk_index, chunks.content,
               chunks.tenant_id, chunks.owner_id
        from chunks join documents on documents.id = chunks.document_id
        where chunks.document_id = ? and documents.lifecycle_status = 'ACTIVE'
        """,
        (document_id,),
    ).fetchall()
    all_entities: list[GraphEntity] = []
    all_relations: list[GraphRelation] = []
    for row in rows:
        entities, relations = extract_graph_from_text(
            row["content"],
            document_id=row["document_id"],
            filename=row["filename"],
            chunk_index=row["chunk_index"],
        )
        all_entities.extend(entities)
        all_relations.extend(relations)
    tenant_id = rows[0]["tenant_id"] if rows else "legacy"
    owner_id = rows[0]["owner_id"] if rows else "legacy"
    _persist(
        all_entities, all_relations, conn=conn,
        tenant_id=tenant_id, owner_id=owner_id,
    )
    _set_meta(
        "last_built_at", _now(), conn=conn,
        tenant_id=tenant_id, owner_id=owner_id,
    )
    return {"entities": len(all_entities), "relations": len(all_relations)}


def rebuild_graph(
    include_tickets: bool = True,
    *,
    tenant_id: str = "legacy",
    owner_id: str | None = "legacy",
) -> dict[str, object]:
    """全量重建，并在单一事务中原子替换旧图。"""
    init_graph_store()
    started_at = perf_counter()
    with database.connect() as conn:
        conn.execute("begin immediate")
        if owner_id is None:
            owner_rows = conn.execute(
                """
                select distinct chunks.owner_id from chunks
                join documents on documents.id = chunks.document_id
                where chunks.tenant_id = ? and documents.lifecycle_status = 'ACTIVE'
                """,
                (tenant_id,),
            ).fetchall()
            owners = {str(row["owner_id"]) for row in owner_rows}
            has_tickets = conn.execute(
                "select name from sqlite_master where type = 'table' and name = 'tickets'"
            ).fetchone()
            if has_tickets:
                owners.update(str(row["owner_id"]) for row in conn.execute(
                    "select distinct owner_id from tickets where tenant_id = ?",
                    (tenant_id,),
                ).fetchall())
            conn.execute("delete from graph_entities where tenant_id = ?", (tenant_id,))
            conn.execute("delete from graph_relations where tenant_id = ?", (tenant_id,))
            conn.execute("delete from graph_meta where tenant_id = ?", (tenant_id,))
            for scope_owner in sorted(owners):
                rows = conn.execute(
                    """
                    select chunks.document_id, chunks.filename, chunks.chunk_index, chunks.content
                    from chunks join documents on documents.id = chunks.document_id
                    where chunks.tenant_id = ? and chunks.owner_id = ?
                      and documents.lifecycle_status = 'ACTIVE'
                    order by chunks.created_at asc, chunks.chunk_index asc
                    """,
                    (tenant_id, scope_owner),
                ).fetchall()
                _replace_graph(
                    conn, rows, include_tickets=include_tickets,
                    tenant_id=tenant_id, owner_id=scope_owner,
                )
            overview = get_graph_overview(conn=conn, tenant_id=tenant_id, owner_id=None)
            overview["duration_ms"] = round((perf_counter() - started_at) * 1000, 2)
            return overview
        rows = conn.execute(
            """
            select chunks.document_id, chunks.filename, chunks.chunk_index, chunks.content
            from chunks join documents on documents.id = chunks.document_id
            where chunks.tenant_id = ? and chunks.owner_id = ?
              and documents.lifecycle_status = 'ACTIVE'
            order by chunks.created_at asc, chunks.chunk_index asc
            """,
            (tenant_id, owner_id),
        ).fetchall()
        _replace_graph(
            conn, rows, include_tickets=include_tickets,
            tenant_id=tenant_id, owner_id=owner_id,
        )
        overview = get_graph_overview(conn=conn, tenant_id=tenant_id, owner_id=owner_id)
    overview["duration_ms"] = round((perf_counter() - started_at) * 1000, 2)
    return overview


def rebuild_graph_scope(
    *,
    conn: sqlite3.Connection,
    tenant_id: str,
    owner_id: str,
) -> None:
    """Replace one authorization scope from currently active documents in the caller's transaction."""
    rows = conn.execute(
        """
        select chunks.document_id, chunks.filename, chunks.chunk_index, chunks.content
        from chunks join documents on documents.id = chunks.document_id
        where chunks.tenant_id = ? and chunks.owner_id = ?
          and documents.lifecycle_status = 'ACTIVE'
        order by chunks.created_at asc, chunks.chunk_index asc
        """,
        (tenant_id, owner_id),
    ).fetchall()
    _replace_graph(
        conn, rows, include_tickets=True, tenant_id=tenant_id, owner_id=owner_id,
    )


def _replace_graph(
    conn: sqlite3.Connection,
    rows: list[sqlite3.Row],
    *,
    include_tickets: bool,
    tenant_id: str,
    owner_id: str,
) -> None:
    all_entities: list[GraphEntity] = []
    all_relations: list[GraphRelation] = []
    for row in rows:
        entities, relations = extract_graph_from_text(
            row["content"],
            document_id=row["document_id"],
            filename=row["filename"],
            chunk_index=row["chunk_index"],
        )
        all_entities.extend(entities)
        all_relations.extend(relations)
    conn.execute(
        "delete from graph_entities where tenant_id = ? and owner_id = ?",
        (tenant_id, owner_id),
    )
    conn.execute(
        "delete from graph_relations where tenant_id = ? and owner_id = ?",
        (tenant_id, owner_id),
    )
    _persist(
        all_entities, all_relations, conn=conn,
        tenant_id=tenant_id, owner_id=owner_id,
    )
    if include_tickets:
        _sync_tickets_into_graph(conn=conn, tenant_id=tenant_id, owner_id=owner_id)
    _set_meta(
        "last_built_at", _now(), conn=conn,
        tenant_id=tenant_id, owner_id=owner_id,
    )


def _sync_tickets_into_graph(
    *,
    conn: sqlite3.Connection | None = None,
    tenant_id: str = "legacy",
    owner_id: str = "legacy",
) -> None:
    """把工单与知识实体连边，演示跨来源关系。"""
    if conn is None:
        with database.connect() as local_conn:
            _sync_tickets_into_graph(
                conn=local_conn, tenant_id=tenant_id, owner_id=owner_id,
            )
        return
    has_tickets = conn.execute(
        "select name from sqlite_master where type = 'table' and name = 'tickets'"
    ).fetchone()
    if not has_tickets:
        return
    tickets = conn.execute(
        """
        select ticket_id, title, description, status from tickets
        where tenant_id = ? and owner_id = ?
        """,
        (tenant_id, owner_id),
    ).fetchall()
    known = conn.execute(
        """
        select name, entity_type from graph_entities
        where tenant_id = ? and owner_id = ?
          and entity_type in ('customer', 'project', 'person')
        """,
        (tenant_id, owner_id),
    ).fetchall()
    for ticket in tickets:
        title = normalize_name(ticket["title"])[:30]
        if not title:
            continue
        text = f"{ticket['title']} {ticket['description']}"
        entity = GraphEntity(name=title, entity_type="ticket", document_ids=[ticket["ticket_id"]])
        relations = [
            GraphRelation(
                source_name=title,
                source_type="ticket",
                relation_type="关联",
                target_name=row["name"],
                target_type=row["entity_type"],
                evidence=ticket["title"][:200],
                document_id=ticket["ticket_id"],
                filename="tickets",
                chunk_index=0,
            )
            for row in known
            if row["name"] in text or row["name"].replace("客户", "") in text
        ]
        _persist(
            [entity], relations, conn=conn,
            tenant_id=tenant_id, owner_id=owner_id,
        )


def delete_document_and_rebuild(
    document_id: str,
    *,
    tenant_id: str | None = None,
    owner_id: str | None = None,
) -> bool:
    """Atomically delete a document and replace the derived graph."""
    init_graph_store()
    with database.connect() as conn:
        conn.execute("begin immediate")
        clauses = ["id = ?"]
        params: list[object] = [document_id]
        if tenant_id is not None:
            clauses.append("tenant_id = ?")
            params.append(tenant_id)
        if owner_id is not None:
            clauses.append("owner_id = ?")
            params.append(owner_id)
        existing = conn.execute(
            f"select id, tenant_id, owner_id, source_type from documents where {' and '.join(clauses)}",
            params,
        ).fetchone()
        if existing is None:
            return False
        if existing["source_type"] == "knowledge":
            return False
        scope_tenant = existing["tenant_id"]
        scope_owner = existing["owner_id"]
        conn.execute("delete from chunks where document_id = ?", (document_id,))
        conn.execute("delete from documents where id = ?", (document_id,))
        database.bump_content_revision(conn, str(scope_tenant))
        rows = conn.execute(
            """
            select chunks.document_id, chunks.filename, chunks.chunk_index, chunks.content
            from chunks join documents on documents.id = chunks.document_id
            where chunks.tenant_id = ? and chunks.owner_id = ?
              and documents.lifecycle_status = 'ACTIVE'
            order by chunks.created_at asc, chunks.chunk_index asc
            """,
            (scope_tenant, scope_owner),
        ).fetchall()
        _replace_graph(
            conn, rows, include_tickets=True,
            tenant_id=scope_tenant, owner_id=scope_owner,
        )
    return True


def remove_document_graph(
    document_id: str,
    *,
    tenant_id: str = "legacy",
    owner_id: str = "legacy",
) -> None:
    """删除文档后重建图（学习版数据量小，重建成本可忽略）。"""
    init_graph_store()
    with database.connect() as conn:
        existing = conn.execute(
            """
            select count(*) as c from graph_relations
            where tenant_id = ? and owner_id = ?
            """,
            (tenant_id, owner_id),
        ).fetchone()
    if existing and existing["c"]:
        rebuild_graph(tenant_id=tenant_id, owner_id=owner_id)


def _set_meta(
    key: str,
    value: str,
    *,
    conn: sqlite3.Connection | None = None,
    tenant_id: str = "legacy",
    owner_id: str = "legacy",
) -> None:
    if conn is None:
        with database.connect() as local_conn:
            _set_meta(
                key, value, conn=local_conn,
                tenant_id=tenant_id, owner_id=owner_id,
            )
        return
    conn.execute(
        """
        insert into graph_meta (tenant_id, owner_id, key, value) values (?, ?, ?, ?)
        on conflict(tenant_id, owner_id, key) do update set value = excluded.value
        """,
        (tenant_id, owner_id, key, value),
    )


def _get_meta(
    key: str,
    *,
    conn: sqlite3.Connection | None = None,
    tenant_id: str = "legacy",
    owner_id: str | None = "legacy",
) -> str:
    if conn is None:
        with database.connect() as local_conn:
            return _get_meta(
                key, conn=local_conn,
                tenant_id=tenant_id, owner_id=owner_id,
            )
    if owner_id is None:
        row = conn.execute(
            "select value from graph_meta where tenant_id = ? and key = ? order by value desc limit 1",
            (tenant_id, key),
        ).fetchone()
    else:
        row = conn.execute(
            "select value from graph_meta where tenant_id = ? and owner_id = ? and key = ?",
            (tenant_id, owner_id, key),
        ).fetchone()
    return row["value"] if row else ""


# ---------------------------------------------------------------------------
# 查询
# ---------------------------------------------------------------------------

def get_graph_overview(
    *,
    conn: sqlite3.Connection | None = None,
    tenant_id: str = "legacy",
    owner_id: str | None = "legacy",
) -> dict[str, object]:
    init_graph_store()
    if conn is None:
        with database.connect() as local_conn:
            return get_graph_overview(
                conn=local_conn, tenant_id=tenant_id, owner_id=owner_id,
            )
    owner_clause = " and owner_id = ?" if owner_id is not None else ""
    scope: tuple[object, ...] = (tenant_id, owner_id) if owner_id is not None else (tenant_id,)
    entity_count = int(conn.execute(
        f"select count(*) from graph_entities where tenant_id = ?{owner_clause}", scope,
    ).fetchone()[0])
    relation_count = int(conn.execute(
        f"select count(*) from graph_relations where tenant_id = ?{owner_clause}", scope,
    ).fetchone()[0])
    type_rows = conn.execute(
        f"""
        select entity_type, count(*) as c from graph_entities
        where tenant_id = ?{owner_clause} group by entity_type
        """,
        scope,
    ).fetchall()
    relation_rows = conn.execute(
        f"""
        select relation_type, count(*) as c from graph_relations
        where tenant_id = ?{owner_clause} group by relation_type
        """,
        scope,
    ).fetchall()
    document_count = int(
        conn.execute(
            f"""
            select count(distinct document_id) from graph_relations
            where tenant_id = ?{owner_clause} and filename != 'tickets'
            """,
            scope,
        ).fetchone()[0]
    )
    return {
        "entity_count": entity_count,
        "relation_count": relation_count,
        "document_count": document_count,
        "entity_types": {row["entity_type"]: row["c"] for row in type_rows},
        "relation_types": {row["relation_type"]: row["c"] for row in relation_rows},
        "built_at": _get_meta(
            "last_built_at", conn=conn, tenant_id=tenant_id, owner_id=owner_id,
        ),
    }


def list_entities(
    entity_type: str = "",
    keyword: str = "",
    limit: int = 100,
    *,
    tenant_id: str = "legacy",
    owner_id: str | None = "legacy",
) -> list[GraphEntity]:
    init_graph_store()
    clauses: list[str] = ["tenant_id = ?"]
    params: list[object] = [tenant_id]
    if owner_id is not None:
        clauses.append("owner_id = ?")
        params.append(owner_id)
    if entity_type:
        clauses.append("entity_type = ?")
        params.append(entity_type)
    if keyword:
        clauses.append("name like ?")
        params.append(f"%{keyword}%")
    where = f" where {' and '.join(clauses)}" if clauses else ""
    with database.connect() as conn:
        rows = conn.execute(
            f"select * from graph_entities{where} order by mention_count desc, name asc", params
        ).fetchall()
    merged: dict[tuple[str, str], GraphEntity] = {}
    for row in rows:
        key = (row["name"], row["entity_type"])
        documents = json.loads(row["document_ids"] or "[]")
        if key not in merged:
            merged[key] = GraphEntity(
                name=row["name"], entity_type=row["entity_type"],
                mention_count=int(row["mention_count"]), document_ids=documents,
            )
        else:
            current = merged[key]
            current.mention_count += int(row["mention_count"])
            current.document_ids = list(dict.fromkeys([*current.document_ids, *documents]))
    return sorted(
        merged.values(), key=lambda item: (-item.mention_count, item.name),
    )[:max(1, min(limit, 500))]


def list_relations(
    entity: str = "",
    relation_type: str = "",
    limit: int = 200,
    *,
    tenant_id: str = "legacy",
    owner_id: str | None = "legacy",
) -> list[GraphRelation]:
    init_graph_store()
    clauses: list[str] = ["tenant_id = ?"]
    params: list[object] = [tenant_id]
    if owner_id is not None:
        clauses.append("owner_id = ?")
        params.append(owner_id)
    if entity:
        clauses.append("(source_name = ? or target_name = ?)")
        params.extend([entity, entity])
    if relation_type:
        clauses.append("relation_type = ?")
        params.append(relation_type)
    where = f" where {' and '.join(clauses)}" if clauses else ""
    params.append(max(1, min(limit, 500)))
    with database.connect() as conn:
        rows = conn.execute(
            f"select * from graph_relations{where} order by created_at asc limit ?", params
        ).fetchall()
    return [_row_to_relation(row) for row in rows]


def find_paths(
    source: str,
    target: str,
    max_depth: int = 3,
    *,
    tenant_id: str = "legacy",
    owner_id: str | None = "legacy",
) -> list[list[GraphPathStep]]:
    """Build the authorized adjacency before traversing any graph edges."""
    init_graph_store()
    adjacency = _build_adjacency(tenant_id=tenant_id, owner_id=owner_id)
    return find_relation_paths(adjacency, source, target, max_depth)


def get_entity_neighborhood(
    names: list[str],
    depth: int = 2,
    limit: int = 24,
    *,
    tenant_id: str = "legacy",
    owner_id: str | None = "legacy",
) -> list[GraphRelation]:
    init_graph_store()
    return relation_neighborhood(
        names, lambda name: list_relations(entity=name, limit=50, tenant_id=tenant_id, owner_id=owner_id),
        depth, limit,
    )


def _build_adjacency(
    *, tenant_id: str = "legacy", owner_id: str | None = "legacy",
) -> dict[str, list[tuple[str, str, bool]]]:
    with database.connect() as conn:
        if owner_id is None:
            rows = conn.execute(
                """
                select source_name, relation_type, target_name from graph_relations
                where tenant_id = ?
                """,
                (tenant_id,),
            ).fetchall()
        else:
            rows = conn.execute(
                """
                select source_name, relation_type, target_name from graph_relations
                where tenant_id = ? and owner_id = ?
                """,
                (tenant_id, owner_id),
            ).fetchall()
    adjacency: dict[str, list[tuple[str, str, bool]]] = {}
    for row in rows:
        adjacency.setdefault(row["source_name"], []).append((row["target_name"], row["relation_type"], True))
        adjacency.setdefault(row["target_name"], []).append((row["source_name"], row["relation_type"], False))
    return adjacency


def _row_to_relation(row: sqlite3.Row) -> GraphRelation:
    return GraphRelation(
        source_name=row["source_name"],
        source_type=row["source_type"],
        relation_type=row["relation_type"],
        target_name=row["target_name"],
        target_type=row["target_type"],
        evidence=row["evidence"],
        document_id=row["document_id"],
        filename=row["filename"],
        chunk_index=int(row["chunk_index"]),
    )
