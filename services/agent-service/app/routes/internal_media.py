import hmac
import os

from fastapi import APIRouter, Depends, Header, HTTPException, status

from app.media_ingestion import (
    IngestionConflictError,
    TranscriptIngestionResponse,
    TranscriptReadyEvent,
    ingest_transcript_event,
)


router = APIRouter(prefix="/internal/v1/media", tags=["internal-media"])


def require_media_service(authorization: str | None = Header(default=None)) -> None:
    expected = os.getenv("MEDIA_INGEST_SERVICE_TOKEN", "").strip()
    if not expected:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Media ingestion service credential is not configured.",
        )
    prefix = "Bearer "
    if authorization is None or not authorization.startswith(prefix):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing media service credential.",
        )
    provided = authorization[len(prefix) :]
    if not hmac.compare_digest(provided.encode("utf-8"), expected.encode("utf-8")):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid media service credential.",
        )


@router.post(
    "/transcripts",
    response_model=TranscriptIngestionResponse,
    status_code=status.HTTP_202_ACCEPTED,
    summary="幂等摄取 Media Service 的 transcript.ready.v1 事件",
)
def ingest_media_transcript(
    event: TranscriptReadyEvent,
    _: None = Depends(require_media_service),
) -> TranscriptIngestionResponse:
    del _
    try:
        return ingest_transcript_event(event)
    except IngestionConflictError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
