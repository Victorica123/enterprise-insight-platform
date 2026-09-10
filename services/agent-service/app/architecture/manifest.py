"""Machine-readable mapping of the architecture panorama to current modules."""

from __future__ import annotations

from dataclasses import asdict, dataclass


@dataclass(frozen=True)
class ArchitectureLayer:
    key: str
    title: str
    responsibility: str
    modules: tuple[str, ...]
    status: str = "implemented"


PANORAMA_LAYERS: tuple[ArchitectureLayer, ...] = (
    ArchitectureLayer(
        "orchestration", "对话编排中心", "路由、问题规划、澄清与阶段检查点", ("architecture.orchestration", "agent_planning", "analysis_store"),
    ),
    ArchitectureLayer(
        "retrieval", "检索与证据", "授权范围内的关键词/向量/混合检索、图谱和引用校验", ("architecture.retrieval", "retrievers", "graph_rag", "citation_review"),
    ),
    ArchitectureLayer(
        "execution", "三层执行器", "确定性领域分析、Agentic RAG 与受控工具执行", ("architecture.execution", "analysis_pipeline", "agentic_rag", "tools"),
    ),
    ArchitectureLayer(
        "knowledge", "知识底座", "文档解析、媒体证据摄取、分块、索引与知识生命周期", ("architecture.knowledge", "rag", "media_ingestion", "knowledge_lifecycle_store"),
    ),
    ArchitectureLayer(
        "governance", "治理与审批", "PRD、知识候选、行动项和审计的人工门禁", ("architecture.governance", "publication_service", "publication_artifacts", "ticket_store"),
    ),
    ArchitectureLayer(
        "guardrails", "工程化护栏", "持久化、缓存、outbox、Trace、保留策略与租户隔离", ("database", "chat_observability_store", "tool_observability_store", "retention"),
    ),
)


def panorama_manifest() -> list[dict[str, object]]:
    """Return serializable architecture metadata for docs/tests, not customer data."""
    return [asdict(layer) for layer in PANORAMA_LAYERS]


__all__ = ["ArchitectureLayer", "PANORAMA_LAYERS", "panorama_manifest"]
