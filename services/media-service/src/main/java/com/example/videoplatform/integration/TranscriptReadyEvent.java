package com.example.videoplatform.integration;

import com.example.videoplatform.transcript.TranscriptResult;
import com.example.videoplatform.workflow.VideoTask;
import com.fasterxml.jackson.annotation.JsonProperty;
import java.time.Instant;
import java.util.List;

public record TranscriptReadyEvent(
		@JsonProperty("event_id") String eventId,
		@JsonProperty("event_type") String eventType,
		@JsonProperty("occurred_at") Instant occurredAt,
		@JsonProperty("trace_id") String traceId,
		@JsonProperty("tenant_id") String tenantId,
		@JsonProperty("owner_id") String ownerId,
		Data data) {

	public static final String EVENT_TYPE = "transcript.ready.v1";

	public static TranscriptReadyEvent from(VideoTask task, Instant occurredAt) {
		TranscriptResult transcript = task.getTranscriptResult();
		List<Segment> segments = transcript.segments().stream()
				.map(segment -> new Segment(
						segment.segmentId(),
						segment.sequence(),
						segment.startMs(),
						segment.endMs(),
						segment.speaker(),
						segment.text()))
				.toList();
		return new TranscriptReadyEvent(
				"transcript:" + task.getTaskId() + ":v" + task.getTranscriptVersion(),
				EVENT_TYPE,
				occurredAt,
				task.getTraceId(),
				task.getTenantId(),
				task.getOwner(),
				new Data(
						task.getVideoId(),
						task.getTranscriptVersion(),
						task.getFileName(),
						transcript.language(),
						transcript.durationMs(),
						segments));
	}

	public record Data(
			@JsonProperty("asset_id") String assetId,
			@JsonProperty("transcript_version") int transcriptVersion,
			String filename,
			String language,
			@JsonProperty("duration_ms") Long durationMs,
			List<Segment> segments) {
	}

	public record Segment(
			@JsonProperty("segment_id") String segmentId,
			int sequence,
			@JsonProperty("start_ms") long startMs,
			@JsonProperty("end_ms") long endMs,
			String speaker,
			String text) {
	}
}
