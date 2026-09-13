from fastapi import APIRouter, Depends, HTTPException

from app.architecture.retrieval import find_paths, get_graph_overview, list_entities, list_relations, rebuild_graph
from app.auth import (
    ActorPrincipal,
    current_principal,
    require_write_role,
)
from app.models import (
    GraphEntityResponse,
    GraphOverviewResponse,
    GraphPathQueryResponse,
    GraphPathResponse,
    GraphPathStepResponse,
    GraphRebuildResponse,
    GraphRelationResponse,
)

router = APIRouter(prefix="/graph", tags=["graph"])


def _graph_scope(principal: ActorPrincipal) -> dict[str, str | None]:
    if principal.auth_mode == "jwt":
        return {"tenant_id": principal.tenant_id, "owner_id": principal.resource_owner_id}
    return {"tenant_id": "legacy", "owner_id": "legacy"}


@router.get("/overview", response_model=GraphOverviewResponse, summary="图谱概览（实体/关系/类型分布）")
def graph_overview(principal: ActorPrincipal = Depends(current_principal)) -> GraphOverviewResponse:
    return GraphOverviewResponse(**get_graph_overview(**_graph_scope(principal)))


@router.get("/entities", response_model=list[GraphEntityResponse], summary="实体列表（类型/关键词过滤）")
def graph_entities(
    entity_type: str = "",
    keyword: str = "",
    limit: int = 100,
    principal: ActorPrincipal = Depends(current_principal),
) -> list[GraphEntityResponse]:
    return [
        GraphEntityResponse(**entity.to_dict())
        for entity in list_entities(entity_type, keyword, limit, **_graph_scope(principal))
    ]


@router.get("/relations", response_model=list[GraphRelationResponse], summary="关系列表（按实体过滤，含证据句）")
def graph_relations(
    entity: str = "",
    relation_type: str = "",
    limit: int = 200,
    principal: ActorPrincipal = Depends(current_principal),
) -> list[GraphRelationResponse]:
    return [
        GraphRelationResponse(**relation.to_dict())
        for relation in list_relations(entity, relation_type, limit, **_graph_scope(principal))
    ]


@router.get("/paths", response_model=GraphPathQueryResponse, summary="两实体间关系链（BFS，最多 4 跳）")
def graph_paths(
    source: str,
    target: str,
    max_depth: int = 3,
    principal: ActorPrincipal = Depends(current_principal),
) -> GraphPathQueryResponse:
    if not source.strip() or not target.strip():
        raise HTTPException(status_code=400, detail="source 和 target 不能为空。")
    paths = find_paths(
        source.strip(), target.strip(), max_depth,
        **_graph_scope(principal),
    )
    return GraphPathQueryResponse(
        source=source.strip(),
        target=target.strip(),
        max_depth=max_depth,
        paths=[
            GraphPathResponse(
                steps=[
                    GraphPathStepResponse(
                        source=step.source,
                        relation=step.relation,
                        target=step.target,
                        forward=step.forward,
                        display=step.display(),
                    )
                    for step in path
                ],
                display=" ; ".join(step.display() for step in path),
            )
            for path in paths
        ],
    )


@router.post("/rebuild", response_model=GraphRebuildResponse, summary="全量重建图谱（operator+）",
             responses={403: {"description": "viewer 无写权限"}})
def graph_rebuild(
    principal: ActorPrincipal = Depends(current_principal),
) -> GraphRebuildResponse:
    require_write_role(principal.role)
    return GraphRebuildResponse(**rebuild_graph(**_graph_scope(principal)))
