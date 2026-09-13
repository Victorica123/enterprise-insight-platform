"""Bounded vector backfill, outside retrieval and outside write transactions."""

from __future__ import annotations

import asyncio
import logging
from hashlib import sha256

from app import database
from app.config import get_settings
from app.embeddings import embed_real, embedding_from_json, embedding_to_json
from app.vector_codec import encode_vector

logger = logging.getLogger(__name__)


def backfill_embeddings_once(batch_size: int = 64) -> int:
    database.init_db()
    with database.connect() as conn:
        rows = conn.execute(
            """
            select c.id, c.document_id, c.tenant_id, c.content, c.chunk_title, c.source_type,
                   c.embedding, c.embedding_v2, c.embedding_blob, c.embedding_v2_blob
            from chunks c join documents d on d.id = c.document_id
            where d.lifecycle_status = 'ACTIVE'
              and (c.embedding_blob is null or c.embedding_v2_blob is null)
            order by case when c.embedding_blob is null then 0
                          when c.embedding_v2 is not null then 1 else 2 end, c.id
            limit ?
            """,
            (max(1, min(batch_size, 512)),),
        ).fetchall()
    if not rows:
        return 0
    missing = [row for row in rows if not row["embedding_v2"] and not row["embedding_v2_blob"]]
    generated = embed_real([row["content"] for row in missing]) if missing else None
    new_vectors = dict(zip((row["id"] for row in missing), generated or [], strict=False))
    updated = 0
    tenants: set[str] = set()
    with database.connect() as conn:
        for row in rows:
            vector = new_vectors.get(row["id"])
            legacy_vector = embedding_from_json(row["embedding_v2"])
            hash_blob = row["embedding_blob"] or encode_vector(embedding_from_json(row["embedding"]))
            real_blob = row["embedding_v2_blob"] or encode_vector(vector if vector is not None else legacy_vector)
            if hash_blob == row["embedding_blob"] and real_blob == row["embedding_v2_blob"]:
                continue
            parent_key = (
                sha256(row["chunk_title"].encode("utf-8")).hexdigest()
                if row["chunk_title"] and row["source_type"] != "video" else ""
            )
            cursor = conn.execute(
                """
                update chunks set embedding_blob = ?, embedding_v2_blob = ?,
                                  embedding_v2 = coalesce(embedding_v2, ?), parent_key = ?
                where id = ? and content = ? and exists (
                    select 1 from documents where id = chunks.document_id and lifecycle_status = 'ACTIVE'
                )
                """,
                (hash_blob, real_blob, embedding_to_json(vector) if vector is not None else None,
                 parent_key, row["id"], row["content"]),
            )
            if cursor.rowcount:
                tenants.add(row["tenant_id"])
                updated += 1
        for tenant in tenants:
            database.bump_content_revision(conn, tenant)
    return updated


async def embedding_backfill_loop() -> None:
    interval = get_settings().embedding_backfill_interval_seconds
    batch_size = min(512, get_settings().embedding_rebuild_batch_size)
    while True:
        # Give startup/health probes priority; never block the event loop on inference.
        await asyncio.sleep(interval)
        try:
            updated = await asyncio.to_thread(backfill_embeddings_once, batch_size)
            if updated:
                logger.info("embedding_backfill_completed chunks=%s", updated)
        except asyncio.CancelledError:
            raise
        except Exception:
            logger.exception("embedding_backfill_failed")
