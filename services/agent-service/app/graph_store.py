"""V4 GraphRAG persistence: rule-based entity/relation extraction into SQLite.

学习版图谱：不依赖 Neo4j，用 SQLite 两张表存实体和关系，
抽取规则针对企业交付类文档（客户/项目/负责人/合同/日期/延期原因/风险条款）。
节点契约独立，后续可平滑迁移到 Neo4j + LLM 抽取。
"""
from __future__ import annotations

import json
import re
import sqlite3
import uuid
from collections import deque
from dataclasses import dataclass, field
from datetime import datetime, timezone
from time import perf_counter

from app import database


ENTITY_TYPE_LABELS = {
    "customer": "客户",
    "project": "项目",
    "person": "人员",
    "contract": "合同",
    "date": "日期",
    "cause": "原因",
    "risk": "风险",
    "ticket": "工单",
}

MAX_PATH_DEPTH = 4
MAX_PATHS = 8

_INITIALIZED_DB_PATH = None


@dataclass
class GraphEntity:
    name: str
    entity_type: str
    mention_count: int = 1
    document_ids: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, object]:
        return {
            "name": self.name,
            "entity_type": self.entity_type,
            "type_label": ENTITY_TYPE_LABELS.get(self.entity_type, self.entity_type),
            "mention_count": self.mention_count,
            "document_ids": self.document_ids,
        }


@dataclass
class GraphRelation:
    source_name: str
    source_type: str
    relation_type: str
    target_name: str
    target_type: str
    evidence: str = ""
    document_id: str = ""
    filename: str = ""
    chunk_index: int = 0

    def to_dict(self) -> dict[str, object]:
        return {
            "source_name": self.source_name,
            "source_type": self.source_type,
            "relation_type": self.relation_type,
            "target_name": self.target_name,
            "target_type": self.target_type,
            "evidence": self.evidence,
            "document_id": self.document_id,
            "filename": self.filename,
            "chunk_index": self.chunk_index,
        }


@dataclass
class GraphPathStep:
    source: str
    relation: str
    target: str
    forward: bool = True

    def display(self) -> str:
        if self.forward:
            return f"{self.source} —{self.relation}→ {self.target}"
        return f"{self.source} ←{self.relation}— {self.target}"


def init_graph_store() -> None:
    global _INITIALIZED_DB_PATH
    current_path = database.DB_PATH.resolve()
    if _INITIALIZED_DB_PATH == current_path and current_path.exists():
        return
    database.DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    with database.connect() as conn:
        conn.execute(
            """
            create table if not exists graph_entities (
                entity_id text primary key,
                name text not null,
                entity_type text not null,
                mention_count integer not null default 1,
                document_ids text not null default '[]',
                created_at text not null,
                unique(name, entity_type)
            )
            """
        )
        conn.execute(
            """
            create table if not exists graph_relations (
                relation_id text primary key,
                source_name text not null,
                source_type text not null,
                relation_type text not null,
                target_name text not null,
                target_type text not null,
                evidence text not null default '',
                document_id text not null default '',
                filename text not null default '',
                chunk_index integer not null default 0,
                created_at text not null,
                unique(source_name, relation_type, target_name, document_id, chunk_index)
            )
            """
        )
        conn.execute("create index if not exists idx_graph_relations_source on graph_relations(source_name)")
        conn.execute("create index if not exists idx_graph_relations_target on graph_relations(target_name)")
        conn.execute(
            """
            create table if not exists graph_meta (
                key text primary key,
                value text not null default ''
            )
            """
        )
    _INITIALIZED_DB_PATH = current_path


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


# ---------------------------------------------------------------------------
# 抽取规则
# ---------------------------------------------------------------------------

DATE_PATTERN = r"\d{4}\s*[年/.-]\s*\d{1,2}\s*[月/.-]\s*\d{1,2}\s*日?"

_STOP_VALUES = {"是", "为", "无", "暂无", "待定", "如下"}

# 字段式文档（如 PDF 抽取后字段串在一行）的边界标签；长标签在前避免误切
_FIELD_BOUNDARY = re.compile(
    r"(?:原计划交付日期|调整后交付日期|项目负责人|延期原因|合同风险|风险提示|风险说明|建议动作|合同编号|负责人|客户|项目)\s*[:：]"
)

_SENTENCE_ENDINGS = "。！？!?；;\n"


def normalize_date(raw: str) -> str:
    numbers = re.findall(r"\d+", raw)
    if len(numbers) < 3:
        return raw.strip()
    return f"{numbers[0]}-{int(numbers[1]):02d}-{int(numbers[2]):02d}"


def normalize_name(raw: str) -> str:
    cleaned = re.sub(r"\s+", "", raw.strip())
    return cleaned.strip("，。；：,.;:！!？?、（）()《》\"'“”‘’")[:40]


def insert_field_boundaries(text: str) -> str:
    """在 `字段:值` 连排文本中补句界，让每个字段独立成句。"""
    parts: list[str] = []
    last = 0
    for match in _FIELD_BOUNDARY.finditer(text):
        start = match.start()
        if start > 0 and text[start - 1] not in _SENTENCE_ENDINGS:
            parts.append(text[last:start])
            parts.append("。")
            last = start
    parts.append(text[last:])
    return "".join(parts)


def split_sentences(text: str) -> list[str]:
    normalized = insert_field_boundaries(text.replace("\r", "\n"))
    parts = re.split(r"(?<=[。！？!?；;\n])", normalized)
    return [part.strip() for part in parts if part.strip()]


def extract_graph_from_text(
    text: str,
    *,
    document_id: str,
    filename: str,
    chunk_index: int,
) -> tuple[list[GraphEntity], list[GraphRelation]]:
    """从一个 chunk 抽取实体与关系；证据取自命中的句子。"""
    entities: dict[tuple[str, str], GraphEntity] = {}
    relations: list[GraphRelation] = []

    def add_entity(name: str, entity_type: str) -> str:
        cleaned = normalize_name(name)
        if not cleaned or cleaned in _STOP_VALUES or len(cleaned) < 2:
            return ""
        key = (cleaned, entity_type)
        if key not in entities:
            entities[key] = GraphEntity(name=cleaned, entity_type=entity_type, document_ids=[document_id])
        else:
            entities[key].mention_count += 1
        return cleaned

    def add_relation(
        source: str, source_type: str, relation_type: str,
        target: str, target_type: str, evidence: str,
    ) -> None:
        if not source or not target or source == target:
            return
        relations.append(
            GraphRelation(
                source_name=source,
                source_type=source_type,
                relation_type=relation_type,
                target_name=target,
                target_type=target_type,
                evidence=evidence.strip()[:200],
                document_id=document_id,
                filename=filename,
                chunk_index=chunk_index,
            )
        )

    sentences = split_sentences(text)
    chunk_customer = ""
    chunk_project = ""
    chunk_contract = ""

    # 第一遍：先找客户 / 项目 / 合同主体，供后续关系挂靠
    for sentence in sentences:
        field_customer = re.search(r"客户\s*[:：]\s*([^\s，,。；;:：]{1,20})", sentence)
        if field_customer:
            name = field_customer.group(1)
            # "甲方客户A" 之类的取从"客户"开始的规范名
            if "客户" in name:
                name = name[name.index("客户"):]
            else:
                name = f"客户{name}"
            chunk_customer = add_entity(name, "customer") or chunk_customer

        narrative_customer = re.search(r"(?:甲方)?客户\s*([A-Za-z0-9甲乙丙丁一二三]{1,6})(?:\s*的|公司|，|。|$)", sentence)
        if narrative_customer and not field_customer:
            chunk_customer = add_entity(f"客户{narrative_customer.group(1)}", "customer") or chunk_customer

        field_project = re.search(r"项目\s*[:：]\s*([^\s，,。；;:：]{1,30})", sentence)
        if field_project:
            chunk_project = add_entity(field_project.group(1), "project") or chunk_project

        if re.search(r"合同", sentence) and not chunk_contract:
            numbered = re.search(r"合同(?:编号)?\s*[:：]\s*([A-Za-z0-9-]{2,30})", sentence)
            chunk_contract = add_entity(numbered.group(1) if numbered else "合同", "contract") or chunk_contract

    # 客户叙述式项目："客户B 的项目" -> 合成项目实体
    if chunk_customer and not chunk_project:
        for sentence in sentences:
            if re.search(rf"{re.escape(chunk_customer.replace('客户', ''))}\s*的项目|客户.{{0,3}}的项目|项目", sentence):
                chunk_project = add_entity(f"{chunk_customer}项目", "project")
                break

    if chunk_customer and chunk_project:
        evidence = next((s for s in sentences if "项目" in s), sentences[0] if sentences else "")
        add_relation(chunk_customer, "customer", "委托", chunk_project, "project", evidence)

    if chunk_project and chunk_contract:
        evidence = next((s for s in sentences if "合同" in s), "")
        add_relation(chunk_project, "project", "涉及合同", chunk_contract, "contract", evidence)

    # 第二遍：逐句抽取具体关系
    for sentence in sentences:
        # 负责人必须带分隔词（:/：/是/为），避免"由负责人准备材料"类误捕
        owner = re.search(
            r"(?:项目)?负责人\s*(?:[:：]|是|为)\s*([一-鿿]{2,4}|[A-Za-z][A-Za-z·\s]{1,18})", sentence
        )
        if owner:
            person = add_entity(owner.group(1), "person")
            if person and chunk_project:
                add_relation(chunk_project, "project", "负责人", person, "person", sentence)

        planned = re.search(rf"(?:原计划(?:交付日期|交付|在)?|计划(?:交付|在))\s*[:：]?\s*({DATE_PATTERN})", sentence)
        if planned:
            date_name = add_entity(normalize_date(planned.group(1)), "date")
            if date_name and chunk_project:
                add_relation(chunk_project, "project", "原计划交付", date_name, "date", sentence)

        adjusted = re.search(
            rf"(?:调整后交付日期|调整后|推迟到|延期到|延迟到|调整为)\s*[:：]?\s*(?:了)?\s*({DATE_PATTERN})", sentence
        )
        if adjusted:
            date_name = add_entity(normalize_date(adjusted.group(1)), "date")
            if date_name and chunk_project:
                add_relation(chunk_project, "project", "调整后交付", date_name, "date", sentence)

        cause_field = re.search(r"延期原因\s*[:：]\s*([^。；\n]{2,40})", sentence)
        cause_narrative = re.search(r"(?:由于|因为|受)\s*([^，,。；;]{2,24}?)\s*(?:影响|导致|造成|[，,。；;])", sentence)
        cause_leading = re.search(r"(?:有人)?([^，,。；;]{2,24}?)(?:导致|造成)(?:了)?[^。]*(?:延期|推迟|延迟)", sentence)
        cause_text = ""
        if cause_field:
            cause_text = cause_field.group(1)
        elif cause_narrative and re.search(r"延期|推迟|延迟|交付", sentence):
            cause_text = cause_narrative.group(1)
        elif cause_leading:
            cause_text = cause_leading.group(1)
        if cause_text:
            cause = add_entity(re.sub(r"^(有人|因|受|由于|因为)", "", cause_text), "cause")
            if cause and chunk_project:
                add_relation(chunk_project, "project", "延期原因", cause, "cause", sentence)

        risk_field = re.search(r"(?:合同风险|风险提示|风险说明)\s*[:：]\s*([^。；\n]{2,60})", sentence)
        risk_clause = re.search(r"合同(?:中)?约定[，,]?\s*([^。\n]{2,60})", sentence)
        risk_text = risk_field.group(1) if risk_field else (risk_clause.group(1) if risk_clause else "")
        if risk_text:
            risk = add_entity(risk_text[:36], "risk")
            holder = chunk_contract or add_entity("合同", "contract")
            if risk and holder:
                add_relation(holder, "contract", "约定", risk, "risk", sentence)
            if risk and chunk_project:
                add_relation(chunk_project, "project", "合同风险", risk, "risk", sentence)

    return list(entities.values()), relations


# ---------------------------------------------------------------------------
# 写入与重建
# ---------------------------------------------------------------------------

def _persist(
    entities: list[GraphEntity],
    relations: list[GraphRelation],
    *,
    conn: sqlite3.Connection | None = None,
) -> None:
    if not entities and not relations:
        return
    if conn is not None:
        _persist_rows(conn, entities, relations)
        return
    with database.connect() as local_conn:
        _persist_rows(local_conn, entities, relations)


def _persist_rows(
    conn: sqlite3.Connection,
    entities: list[GraphEntity],
    relations: list[GraphRelation],
) -> None:
    now = _now()
    for entity in entities:
        row = conn.execute(
            "select entity_id, mention_count, document_ids from graph_entities where name = ? and entity_type = ?",
            (entity.name, entity.entity_type),
        ).fetchone()
        if row is None:
            conn.execute(
                """
                insert into graph_entities (entity_id, name, entity_type, mention_count, document_ids, created_at)
                values (?, ?, ?, ?, ?, ?)
                """,
                (
                    str(uuid.uuid4()),
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
                relation_id, source_name, source_type, relation_type,
                target_name, target_type, evidence, document_id, filename, chunk_index, created_at
            ) values (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                str(uuid.uuid4()),
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
        "select document_id, filename, chunk_index, content from chunks where document_id = ?",
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
    _persist(all_entities, all_relations, conn=conn)
    _set_meta("last_built_at", _now(), conn=conn)
    return {"entities": len(all_entities), "relations": len(all_relations)}


def rebuild_graph(include_tickets: bool = True) -> dict[str, object]:
    """全量重建，并在单一事务中原子替换旧图。"""
    init_graph_store()
    started_at = perf_counter()
    with database.connect() as conn:
        conn.execute("begin immediate")
        rows = conn.execute(
            "select document_id, filename, chunk_index, content from chunks order by created_at asc, chunk_index asc"
        ).fetchall()
        _replace_graph(conn, rows, include_tickets=include_tickets)
        overview = get_graph_overview(conn=conn)
    overview["duration_ms"] = round((perf_counter() - started_at) * 1000, 2)
    return overview


def _replace_graph(
    conn: sqlite3.Connection,
    rows: list[sqlite3.Row],
    *,
    include_tickets: bool,
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
    conn.execute("delete from graph_entities")
    conn.execute("delete from graph_relations")
    _persist(all_entities, all_relations, conn=conn)
    if include_tickets:
        _sync_tickets_into_graph(conn=conn)
    _set_meta("last_built_at", _now(), conn=conn)


def _sync_tickets_into_graph(*, conn: sqlite3.Connection | None = None) -> None:
    """把工单与知识实体连边，演示跨来源关系。"""
    if conn is None:
        with database.connect() as local_conn:
            _sync_tickets_into_graph(conn=local_conn)
        return
    has_tickets = conn.execute(
        "select name from sqlite_master where type = 'table' and name = 'tickets'"
    ).fetchone()
    if not has_tickets:
        return
    tickets = conn.execute("select ticket_id, title, description, status from tickets").fetchall()
    known = conn.execute(
        "select name, entity_type from graph_entities where entity_type in ('customer', 'project', 'person')"
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
        _persist([entity], relations, conn=conn)


def delete_document_and_rebuild(document_id: str) -> bool:
    """Atomically delete a document and replace the derived graph."""
    init_graph_store()
    with database.connect() as conn:
        conn.execute("begin immediate")
        existing = conn.execute("select id from documents where id = ?", (document_id,)).fetchone()
        if existing is None:
            return False
        conn.execute("delete from chunks where document_id = ?", (document_id,))
        conn.execute("delete from documents where id = ?", (document_id,))
        database.bump_content_revision(conn)
        rows = conn.execute(
            "select document_id, filename, chunk_index, content from chunks order by created_at asc, chunk_index asc"
        ).fetchall()
        _replace_graph(conn, rows, include_tickets=True)
    return True


def remove_document_graph(document_id: str) -> None:
    """删除文档后重建图（学习版数据量小，重建成本可忽略）。"""
    init_graph_store()
    with database.connect() as conn:
        existing = conn.execute("select count(*) as c from graph_relations").fetchone()
    if existing and existing["c"]:
        rebuild_graph()


def _set_meta(key: str, value: str, *, conn: sqlite3.Connection | None = None) -> None:
    if conn is None:
        with database.connect() as local_conn:
            _set_meta(key, value, conn=local_conn)
        return
    conn.execute(
        "insert into graph_meta (key, value) values (?, ?) on conflict(key) do update set value = excluded.value",
        (key, value),
    )


def _get_meta(key: str, *, conn: sqlite3.Connection | None = None) -> str:
    if conn is None:
        with database.connect() as local_conn:
            return _get_meta(key, conn=local_conn)
    row = conn.execute("select value from graph_meta where key = ?", (key,)).fetchone()
    return row["value"] if row else ""


# ---------------------------------------------------------------------------
# 查询
# ---------------------------------------------------------------------------

def get_graph_overview(*, conn: sqlite3.Connection | None = None) -> dict[str, object]:
    init_graph_store()
    if conn is None:
        with database.connect() as local_conn:
            return get_graph_overview(conn=local_conn)
    entity_count = int(conn.execute("select count(*) from graph_entities").fetchone()[0])
    relation_count = int(conn.execute("select count(*) from graph_relations").fetchone()[0])
    type_rows = conn.execute(
        "select entity_type, count(*) as c from graph_entities group by entity_type"
    ).fetchall()
    relation_rows = conn.execute(
        "select relation_type, count(*) as c from graph_relations group by relation_type"
    ).fetchall()
    document_count = int(
        conn.execute(
            "select count(distinct document_id) from graph_relations where filename != 'tickets'"
        ).fetchone()[0]
    )
    return {
        "entity_count": entity_count,
        "relation_count": relation_count,
        "document_count": document_count,
        "entity_types": {row["entity_type"]: row["c"] for row in type_rows},
        "relation_types": {row["relation_type"]: row["c"] for row in relation_rows},
        "built_at": _get_meta("last_built_at", conn=conn),
    }


def list_entities(entity_type: str = "", keyword: str = "", limit: int = 100) -> list[GraphEntity]:
    init_graph_store()
    clauses: list[str] = []
    params: list[object] = []
    if entity_type:
        clauses.append("entity_type = ?")
        params.append(entity_type)
    if keyword:
        clauses.append("name like ?")
        params.append(f"%{keyword}%")
    where = f" where {' and '.join(clauses)}" if clauses else ""
    params.append(max(1, min(limit, 500)))
    with database.connect() as conn:
        rows = conn.execute(
            f"select * from graph_entities{where} order by mention_count desc, name asc limit ?", params
        ).fetchall()
    return [
        GraphEntity(
            name=row["name"],
            entity_type=row["entity_type"],
            mention_count=int(row["mention_count"]),
            document_ids=json.loads(row["document_ids"] or "[]"),
        )
        for row in rows
    ]


def list_relations(entity: str = "", relation_type: str = "", limit: int = 200) -> list[GraphRelation]:
    init_graph_store()
    clauses: list[str] = []
    params: list[object] = []
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


def find_paths(source: str, target: str, max_depth: int = 3) -> list[list[GraphPathStep]]:
    """无向 BFS 找两个实体之间的关系链（返回带方向标注的路径）。"""
    init_graph_store()
    max_depth = max(1, min(max_depth, MAX_PATH_DEPTH))
    adjacency = _build_adjacency()
    if source not in adjacency or target not in adjacency:
        return []

    paths: list[list[GraphPathStep]] = []
    queue: deque[tuple[str, list[GraphPathStep], set[str]]] = deque([(source, [], {source})])
    while queue and len(paths) < MAX_PATHS:
        node, path, visited = queue.popleft()
        if len(path) >= max_depth:
            continue
        for neighbor, relation_type, forward in adjacency.get(node, []):
            if neighbor in visited:
                continue
            step = (
                GraphPathStep(source=node, relation=relation_type, target=neighbor, forward=True)
                if forward
                else GraphPathStep(source=node, relation=relation_type, target=neighbor, forward=False)
            )
            next_path = path + [step]
            if neighbor == target:
                paths.append(next_path)
                continue
            queue.append((neighbor, next_path, visited | {neighbor}))
    return paths


def get_entity_neighborhood(names: list[str], depth: int = 2, limit: int = 24) -> list[GraphRelation]:
    """取一组实体周边 depth 跳内的关系，供 Graph Agent 组装上下文。"""
    init_graph_store()
    depth = max(1, min(depth, MAX_PATH_DEPTH))
    frontier = {name for name in names if name}
    if not frontier:
        return []
    seen_relations: dict[tuple[str, str, str], GraphRelation] = {}
    visited: set[str] = set()
    for _ in range(depth):
        if not frontier or len(seen_relations) >= limit:
            break
        batch = [name for name in frontier if name not in visited]
        visited.update(batch)
        next_frontier: set[str] = set()
        for name in batch:
            for relation in list_relations(entity=name, limit=50):
                key = (relation.source_name, relation.relation_type, relation.target_name)
                if key not in seen_relations:
                    seen_relations[key] = relation
                next_frontier.add(relation.source_name)
                next_frontier.add(relation.target_name)
        frontier = next_frontier - visited
    return list(seen_relations.values())[:limit]


def _build_adjacency() -> dict[str, list[tuple[str, str, bool]]]:
    with database.connect() as conn:
        rows = conn.execute("select source_name, relation_type, target_name from graph_relations").fetchall()
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
