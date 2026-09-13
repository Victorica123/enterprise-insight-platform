"""Versioned little-endian float32 vectors, with a legacy JSON read path."""

from __future__ import annotations

import math
import struct
from collections.abc import Sequence

from app.embeddings import embedding_from_json

_MAGIC = b"EIV1"
_MAX_DIMENSION = 16_384


def encode_vector(vector: Sequence[float] | None) -> bytes | None:
    if not vector:
        return None
    if len(vector) > _MAX_DIMENSION or any(not math.isfinite(value) for value in vector):
        raise ValueError("Embedding must contain a bounded, finite vector.")
    return _MAGIC + struct.pack(f"<{len(vector)}f", *vector)


def decode_vector(blob: bytes | memoryview | None, legacy: str | None = None) -> list[float] | None:
    if isinstance(blob, (bytes, memoryview)):
        raw = bytes(blob)
        length = len(raw) - len(_MAGIC)
        if raw.startswith(_MAGIC) and 0 < length <= _MAX_DIMENSION * 4 and length % 4 == 0:
            vector = list(struct.unpack(f"<{length // 4}f", raw[len(_MAGIC):]))
            if all(math.isfinite(value) for value in vector):
                return vector
    # Existing databases and rollback readers keep working during dual writes.
    return embedding_from_json(legacy)
