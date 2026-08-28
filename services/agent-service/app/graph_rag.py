"""V4 Graph Agent: 把关系图谱接入 Agentic 工作流。

职责：识别问题里的图谱实体 -> 取周边子图 -> 组装关系链上下文与风险链，
供 Answer Agent 注入回答，并在 trace 中留下可回放的记录。
"""
from __future__ import annotations

from dataclasses import dataclass, field

from app.graph_store import (
    ENTITY_TYPE_LABELS,
    GraphRelation,
    get_entity_neighborhood,
    list_entities,
)


RELATION_INTENT_KEYWORDS = [
    "关系", "关联", "相关", "涉及", "之间", "链路", "图谱",
    "哪些", "谁", "责任", "归属", "影响", "牵连",
]

RISK_RELATION_TYPES = {"延期原因", "合同风险", "约定"}


@dataclass
class GraphLookup:
    matched_entities: list[str] = field(default_factory=list)
    relations: list[GraphRelation] = field(default_factory=list)
    paths: list[str] = field(default_factory=list)
    risk_chains: list[str] = field(default_factory=list)
    context: str = ""

    @property
    def hit(self) -> bool:
        return bool(self.relations)


def question_wants_graph(question: str, intent: str) -> bool:
    """关系类问题、风险/因果类问题都值得查图。"""
    if any(keyword in question for keyword in RELATION_INTENT_KEYWORDS):
        return True
    return intent in {"risk", "causal", "fact"}


def match_question_entities(question: str, limit: int = 4) -> list[str]:
    """把问题文本和已知实体名做双向包含匹配。"""
    compact = question.replace(" ", "")
    matched: list[str] = []
    for entity in list_entities(limit=300):
        name = entity.name
        stripped = name.replace("客户", "")
        if name in compact or (len(stripped) >= 1 and f"客户{stripped}" in compact) or (
            len(name) >= 3 and name[:3] in compact
        ):
            if name not in matched:
                matched.append(name)
        if len(matched) >= limit:
            break
    return matched


def lookup_graph(question: str, intent: str) -> GraphLookup:
    lookup = GraphLookup()
    if not question_wants_graph(question, intent):
        return lookup

    lookup.matched_entities = match_question_entities(question)
    if not lookup.matched_entities:
        return lookup

    lookup.relations = get_entity_neighborhood(lookup.matched_entities, depth=2, limit=24)
    if not lookup.relations:
        return lookup

    lookup.paths = [format_relation(relation) for relation in lookup.relations]
    lookup.risk_chains = build_risk_chains(lookup.relations)
    lookup.context = build_graph_context(lookup)
    return lookup


def format_relation(relation: GraphRelation) -> str:
    return f"{relation.source_name} —{relation.relation_type}→ {relation.target_name}"


def build_risk_chains(relations: list[GraphRelation]) -> list[str]:
    """把延期原因 / 合同风险 / 合同约定串成风险链路。"""
    chains: list[str] = []
    for relation in relations:
        if relation.relation_type in RISK_RELATION_TYPES:
            label = ENTITY_TYPE_LABELS.get(relation.target_type, relation.target_type)
            chains.append(f"{format_relation(relation)}（{label}）")
    return chains


def build_graph_context(lookup: GraphLookup) -> str:
    parts = ["【关系图谱】"]
    parts.append(f"命中实体：{'、'.join(lookup.matched_entities)}")
    for relation in lookup.relations[:12]:
        origin = f"{relation.filename} #chunk{relation.chunk_index}" if relation.filename else "工单"
        parts.append(f"- {format_relation(relation)}（来源：{origin}）")
    if lookup.risk_chains:
        parts.append("风险链路：")
        parts.extend(f"- {chain}" for chain in lookup.risk_chains[:6])
    return "\n".join(parts)
