from app.models import Source


def format_timestamp(milliseconds: int) -> str:
    total_seconds, millis = divmod(milliseconds, 1000)
    hours, remainder = divmod(total_seconds, 3600)
    minutes, seconds = divmod(remainder, 60)
    prefix = f"{hours:02d}:{minutes:02d}:{seconds:02d}" if hours else f"{minutes:02d}:{seconds:02d}"
    return f"{prefix}.{millis:03d}" if millis else prefix


def source_location(source: Source) -> str:
    if source.source_type == "video":
        start = format_timestamp(source.start_ms or 0)
        end = format_timestamp(source.end_ms or source.start_ms or 0)
        speaker = f" · {source.speaker}" if source.speaker else ""
        return f"{source.filename} · {start}–{end}{speaker}"
    title = f" / {source.title}" if source.title else ""
    return f"{source.filename} / chunk {source.chunk_index}{title}"
