from __future__ import annotations

import hashlib
import json
from datetime import datetime
from typing import Literal
from uuid import NAMESPACE_URL, uuid5

from pydantic import BaseModel, Field, field_validator, model_validator

from app import database


class TranscriptSegment(BaseModel):
    segment_id: str = Field(min_length=1, max_length=128)
    sequence: int = Field(ge=0)
    start_ms: int = Field(ge=0)
    end_ms: int = Field(ge=0)
    speaker: str | None = Field(default=None, max_length=128)
    text: str = Field(min_length=1, max_length=20_000)

    @field_validator("segment_id", "text")
    @classmethod
    def strip_required_text(cls, value: str) -> str:
        stripped = value.strip()
        if not stripped:
            raise ValueError("must not be blank")
        return stripped

    @field_validator("speaker")
    @classmethod
    def strip_optional_text(cls, value: str | None) -> str | None:
        if value is None:
            return None
        return value.strip() or None

    @model_validator(mode="after")
    def validate_time_range(self) -> TranscriptSegment:
        if self.end_ms < self.start_ms:
            raise ValueError("end_ms must be greater than or equal to start_ms")
        return self


class TranscriptData(BaseModel):
    asset_id: str = Field(min_length=1, max_length=128)
    transcript_version: int = Field(ge=1)
    filename: str = Field(min_length=1, max_length=512)
    language: str | None = Field(default=None, max_length=32)
    duration_ms: int | None = Field(default=None, ge=0)
    segments: list[TranscriptSegment] = Field(max_length=20_000)

    @field_validator("asset_id", "filename")
    @classmethod
    def strip_required_text(cls, value: str) -> str:
        stripped = value.strip()
        if not stripped:
            raise ValueError("must not be blank")
        return stripped

    @model_validator(mode="after")
    def validate_segments(self) -> TranscriptData:
        identifiers: set[str] = set()
        previous_start = -1
        for index, segment in enumerate(self.segments):
            if segment.sequence != index:
                raise ValueError("segment sequence must be contiguous and start at zero")
            if segment.segment_id in identifiers:
                raise ValueError("segment_id must be unique within a transcript")
            if segment.start_ms < previous_start:
                raise ValueError("segments must be ordered by start_ms")
            if self.duration_ms is not None and segment.end_ms > self.duration_ms:
                raise ValueError("segment end_ms exceeds duration_ms")
            identifiers.add(segment.segment_id)
            previous_start = segment.start_ms
        return self


class TranscriptReadyEvent(BaseModel):
    event_id: str = Field(min_length=1, max_length=128)
    event_type: Literal["transcript.ready.v1"]
    occurred_at: datetime
    trace_id: str = Field(min_length=1, max_length=128)
    tenant_id: str = Field(min_length=1, max_length=128)
    owner_id: str = Field(min_length=1, max_length=128)
    data: TranscriptData

    @field_validator("event_id", "trace_id", "tenant_id", "owner_id")
    @classmethod
    def strip_identifiers(cls, value: str) -> str:
        stripped = value.strip()
        if not stripped:
            raise ValueError("must not be blank")
        return stripped

    @field_validator("occurred_at")
    @classmethod
    def require_timezone(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("occurred_at must include a timezone")
        return value


class TranscriptIngestionResponse(BaseModel):
    status: Literal["ingested", "duplicate"]
    event_id: str
    document_id: str
    asset_id: str
    transcript_version: int
    segment_count: int


class IngestionConflictError(ValueError):
    pass


def _canonical_sha256(value: object) -> str:
    raw = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def _segment_title(segment: TranscriptSegment) -> str:
    start = _format_time(segment.start_ms)
    end = _format_time(segment.end_ms)
    speaker = f" · {segment.speaker}" if segment.speaker else ""
    return f"{start}–{end}{speaker}"


def _format_time(milliseconds: int) -> str:
    total_seconds = milliseconds // 1000
    hours, remainder = divmod(total_seconds, 3600)
    minutes, seconds = divmod(remainder, 60)
    if hours:
        return f"{hours:02d}:{minutes:02d}:{seconds:02d}"
    return f"{minutes:02d}:{seconds:02d}"


def ingest_transcript_event(event: TranscriptReadyEvent) -> TranscriptIngestionResponse:
    database.init_db()
    event_payload = event.model_dump(mode="json")
    event_sha256 = _canonical_sha256(event_payload)
    content_sha256 = _canonical_sha256(
        {
            "tenant_id": event.tenant_id,
            "owner_id": event.owner_id,
            "data": event.data.model_dump(mode="json"),
        }
    )
    document_id = str(
        uuid5(
            NAMESPACE_URL,
            f"enterprise-insight:{event.tenant_id}:video:{event.data.asset_id}:{event.data.transcript_version}",
        )
    )

    with database.connect() as conn:
        receipt = database.get_ingestion_receipt(event.event_id, conn=conn)
        if receipt is not None:
            if receipt["payload_sha256"] != event_sha256:
                raise IngestionConflictError("event_id was already used with a different payload")
            return _response(event, "duplicate", receipt["document_id"])

        existing = database.find_evidence_document(
            event.tenant_id,
            "video",
            event.data.asset_id,
            event.data.transcript_version,
            conn=conn,
        )
        if existing is not None:
            if existing["payload_sha256"] != content_sha256:
                raise IngestionConflictError(
                    "asset transcript version already exists with different content"
                )
            database.insert_ingestion_receipt(
                event_id=event.event_id,
                event_type=event.event_type,
                tenant_id=event.tenant_id,
                resource_id=event.data.asset_id,
                resource_version=event.data.transcript_version,
                payload_sha256=event_sha256,
                document_id=existing["id"],
                trace_id=event.trace_id,
                conn=conn,
            )
            return _response(event, "duplicate", existing["id"])

        chunks = [(_segment_title(segment), segment.text) for segment in event.data.segments]
        chunk_metadata = [
            {
                "asset_id": event.data.asset_id,
                "segment_id": segment.segment_id,
                "start_ms": segment.start_ms,
                "end_ms": segment.end_ms,
                "speaker": segment.speaker,
            }
            for segment in event.data.segments
        ]
        database.insert_document(
            document_id=document_id,
            filename=event.data.filename,
            chunks=chunks,
            conn=conn,
            tenant_id=event.tenant_id,
            owner_id=event.owner_id,
            source_type="video",
            external_id=event.data.asset_id,
            source_version=event.data.transcript_version,
            payload_sha256=content_sha256,
            metadata={
                "language": event.data.language,
                "duration_ms": event.data.duration_ms,
                "trace_id": event.trace_id,
                "occurred_at": event.occurred_at.isoformat(),
            },
            chunk_metadata=chunk_metadata,
        )
        database.insert_ingestion_receipt(
            event_id=event.event_id,
            event_type=event.event_type,
            tenant_id=event.tenant_id,
            resource_id=event.data.asset_id,
            resource_version=event.data.transcript_version,
            payload_sha256=event_sha256,
            document_id=document_id,
            trace_id=event.trace_id,
            conn=conn,
        )

    return _response(event, "ingested", document_id)


def _response(
    event: TranscriptReadyEvent,
    status: Literal["ingested", "duplicate"],
    document_id: str,
) -> TranscriptIngestionResponse:
    return TranscriptIngestionResponse(
        status=status,
        event_id=event.event_id,
        document_id=document_id,
        asset_id=event.data.asset_id,
        transcript_version=event.data.transcript_version,
        segment_count=len(event.data.segments),
    )
