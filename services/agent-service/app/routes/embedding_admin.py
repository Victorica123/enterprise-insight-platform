"""Embedding 管理端点。全库重嵌入是重操作，仅 operator/admin 可触发。"""
from fastapi import APIRouter, Header

from app.auth import require_write_role, validate_actor_role
from app.database import get_embedding_stats, rebuild_chunk_embeddings
from app.models import EmbeddingRebuildResponse, EmbeddingStatus
from app.status_service import build_embedding_status


router = APIRouter(tags=["embeddings"])


@router.get("/embeddings/status", response_model=EmbeddingStatus, summary="Embedding 覆盖率状态")
def get_embeddings_status() -> EmbeddingStatus:
    return build_embedding_status(get_embedding_stats())


@router.post("/embeddings/rebuild", response_model=EmbeddingRebuildResponse, summary="全量重建 embedding（operator+）",
             responses={403: {"description": "viewer 无写权限"}})
def rebuild_embeddings(x_user_role: str = Header(default="viewer")) -> EmbeddingRebuildResponse:
    require_write_role(validate_actor_role(x_user_role))
    stats = rebuild_chunk_embeddings()
    status = build_embedding_status(stats)
    return EmbeddingRebuildResponse(
        total_chunks=status.total_chunks,
        embedded_chunks=status.embedded_chunks,
        missing_chunks=status.missing_chunks,
        coverage=status.coverage,
        embedded_chunks_v2=status.embedded_chunks_v2,
        missing_chunks_v2=status.missing_chunks_v2,
        updated_chunks=stats["updated_chunks"],
    )
