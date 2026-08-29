from app.embeddings import get_real_embedding_cache_stats
from app.models import CacheMetric, CacheObservability, EmbeddingCoverageStatus, EmbeddingStatus
from app.retrievers import get_chunk_cache_stats


def build_cache_metric(stats: dict[str, int]) -> CacheMetric:
    hits = max(0, int(stats.get("hits", 0)))
    misses = max(0, int(stats.get("misses", 0)))
    requests = hits + misses
    return CacheMetric(
        entries=max(0, int(stats.get("entries", 0))),
        max_entries=max(0, int(stats.get("max_entries", 0))),
        hits=hits,
        misses=misses,
        requests=requests,
        hit_rate=hits / requests if requests else 0.0,
    )


def build_embedding_coverage(stats: dict[str, int]) -> EmbeddingCoverageStatus:
    total_chunks = stats["total_chunks"]
    embedded_chunks = stats["embedded_chunks"]
    coverage = embedded_chunks / total_chunks if total_chunks else 1.0
    return EmbeddingCoverageStatus(
        total_chunks=total_chunks,
        embedded_chunks=embedded_chunks,
        missing_chunks=stats["missing_chunks"],
        coverage=coverage,
        embedded_chunks_v2=stats.get("embedded_chunks_v2", 0),
        missing_chunks_v2=stats.get("missing_chunks_v2", 0),
    )


def build_embedding_status(
    stats: dict[str, int],
    *,
    embedding_cache_stats: dict[str, int] | None = None,
    chunk_cache_stats: dict[str, int] | None = None,
) -> EmbeddingStatus:
    coverage = build_embedding_coverage(stats)
    return EmbeddingStatus(
        **coverage.model_dump(),
        cache=CacheObservability(
            embedding_vectors=build_cache_metric(
                embedding_cache_stats if embedding_cache_stats is not None else get_real_embedding_cache_stats()
            ),
            chunk_snapshots=build_cache_metric(
                chunk_cache_stats if chunk_cache_stats is not None else get_chunk_cache_stats()
            ),
        ),
    )
