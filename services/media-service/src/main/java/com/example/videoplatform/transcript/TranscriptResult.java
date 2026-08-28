package com.example.videoplatform.transcript;

import com.fasterxml.jackson.core.type.TypeReference;
import com.fasterxml.jackson.databind.ObjectMapper;
import java.util.List;

/** Version-one timestamped transcript used by persistence and transcript.ready.v1. */
public record TranscriptResult(String text, List<Segment> segments, String language, Long durationMs) {

	private static final ObjectMapper JSON = new ObjectMapper();
	private static final TypeReference<List<Segment>> SEGMENT_LIST = new TypeReference<>() { };

	public TranscriptResult {
		text = text == null ? "" : text.strip();
		segments = segments == null ? List.of() : List.copyOf(segments);
		language = language == null || language.isBlank() ? null : language.strip();
		if (durationMs != null && durationMs < 0) {
			throw new IllegalArgumentException("durationMs must be non-negative");
		}
		long previousStart = -1;
		for (int index = 0; index < segments.size(); index++) {
			Segment segment = segments.get(index);
			if (segment.sequence() != index || segment.startMs() < previousStart) {
				throw new IllegalArgumentException("segments must be contiguous and ordered");
			}
			if (durationMs != null && segment.endMs() > durationMs) {
				throw new IllegalArgumentException("segment exceeds transcript duration");
			}
			previousStart = segment.startMs();
		}
	}

	public static TranscriptResult fromPlainText(String text) {
		String normalized = text == null ? "" : text.strip();
		List<Segment> fallback = normalized.isEmpty()
				? List.of()
				: List.of(new Segment("segment-0", 0, 0, 0, null, normalized));
		return new TranscriptResult(normalized, fallback, null, null);
	}

	public String segmentsJson() {
		try {
			return JSON.writeValueAsString(segments);
		} catch (Exception exception) {
			throw new IllegalStateException("Unable to serialize transcript segments", exception);
		}
	}

	public static TranscriptResult fromStored(String text, String segmentsJson, String language, Long durationMs) {
		if (segmentsJson == null || segmentsJson.isBlank()) {
			return fromPlainText(text);
		}
		try {
			return new TranscriptResult(text, JSON.readValue(segmentsJson, SEGMENT_LIST), language, durationMs);
		} catch (Exception exception) {
			throw new IllegalStateException("Unable to deserialize stored transcript segments", exception);
		}
	}

	public record Segment(String segmentId, int sequence, long startMs, long endMs, String speaker, String text) {
		public Segment {
			if (segmentId == null || segmentId.isBlank()) {
				throw new IllegalArgumentException("segmentId is required");
			}
			segmentId = segmentId.strip();
			if (sequence < 0 || startMs < 0 || endMs < startMs) {
				throw new IllegalArgumentException("invalid segment sequence or time range");
			}
			speaker = speaker == null || speaker.isBlank() ? null : speaker.strip();
			if (text == null || text.isBlank()) {
				throw new IllegalArgumentException("segment text is required");
			}
			text = text.strip();
		}
	}
}
