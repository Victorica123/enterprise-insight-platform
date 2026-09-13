"""Embedding 管理端点。全库重嵌入是重操作，仅 operator/admin 可触发。"""
from fastapi import APIRouter, Depends

from app.architecture.knowledge import build_embedding_status, get_embedding_stats, rebuild_chunk_embeddings
from app.auth import ActorPrincipal, current_principal, require_write_role
from app.models import EmbeddingRebuildResponse, EmbeddingStatus

router = APIRouter(tags=["embeddings"])


@router.get("/embeddings/status", response_model=EmbeddingStatus, summary="Embedding 覆盖率与进程缓存状态")
def get_embeddings_status(_: ActorPrincipal = Depends(current_principal)) -> EmbeddingStatus:
    return build_embedding_status(get_embedding_stats())


@router.post("/embeddings/rebuild", response_model=EmbeddingRebuildResponse, summary="全量重建 embedding（operator+）",
             responses={403: {"description": "viewer 无写权限"}})
def rebuild_embeddings(
    principal: ActorPrincipal = Depends(current_principal),
) -> EmbeddingRebuildResponse:
    require_write_role(principal.role)
    stats = rebuild_chunk_embeddings()
    status = build_embedding_status(stats)
    return EmbeddingRebuildResponse(
        total_chunks=status.total_chunks,
        embedded_chunks=status.embedded_chunks,
        missing_chunks=status.missing_chunks,
        coverage=status.coverage,
        embedded_chunks_v2=status.embedded_chunks_v2,
        missing_chunks_v2=status.missing_chunks_v2,
        cache=status.cache,
        updated_chunks=stats["updated_chunks"],
    )
