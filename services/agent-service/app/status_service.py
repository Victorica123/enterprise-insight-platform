from app.models import EmbeddingStatus


def build_embedding_status(stats: dict[str, int]) -> EmbeddingStatus:
    total_chunks = stats["total_chunks"]
    embedded_chunks = stats["embedded_chunks"]
    coverage = embedded_chunks / total_chunks if total_chunks else 1.0
    return EmbeddingStatus(
        total_chunks=total_chunks,
        embedded_chunks=embedded_chunks,
        missing_chunks=stats["missing_chunks"],
        coverage=coverage,
        embedded_chunks_v2=stats.get("embedded_chunks_v2", 0),
        missing_chunks_v2=stats.get("missing_chunks_v2", 0),
    )
