"""Knowledge-base boundary (知识底座)."""

from app.database import get_embedding_stats, rebuild_chunk_embeddings
from app.document_parser import is_supported_file, parse_document
from app.media_ingestion import (
    IngestionConflictError,
    TranscriptData,
    TranscriptIngestionResponse,
    TranscriptReadyEvent,
    TranscriptSegment,
    ingest_transcript_event,
)
from app.rag import delete_document, ingest_document, list_documents
from app.status_service import build_embedding_status

__all__ = [
    'TranscriptIngestionResponse',
    'build_embedding_status',
    'get_embedding_stats', 'rebuild_chunk_embeddings',
    "IngestionConflictError",
    "TranscriptData",
    "TranscriptReadyEvent",
    "TranscriptSegment",
    "delete_document",
    "ingest_document",
    "ingest_transcript_event",
    "is_supported_file",
    "list_documents",
    "parse_document",
]
