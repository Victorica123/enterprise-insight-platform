"""Deterministic entity and relation extraction for the local GraphRAG baseline.

This module contains no persistence. It turns one authorized text chunk into
typed graph facts that graph_store.py can atomically persist and rebuild.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field

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

DATE_PATTERN = r"\d{4}\s*[年/.-]\s*\d{1,2}\s*[月/.-]\s*\d{1,2}\s*日?"

_STOP_VALUES = {"是", "为", "无", "暂无", "待定", "如下"}

# 字段式文档（如 PDF 抽取后字段串在一行）的边界标签；长标签在前避免误切。
_FIELD_BOUNDARY = re.compile(
    r"(?:原计划交付日期|调整后交付日期|项目负责人|延期原因|合同风险|风险提示|风险说明|建议动作|合同编号|负责人|客户|项目)\s*[:：]"
)

_SENTENCE_ENDINGS = "。！？!?；;\n"

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
