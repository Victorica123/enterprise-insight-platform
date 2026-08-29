package com.example.videoplatform.integration;

import static org.assertj.core.api.Assertions.assertThat;

import com.example.videoplatform.transcript.TranscriptResult;
import com.example.videoplatform.workflow.VideoTask;
import com.fasterxml.jackson.databind.json.JsonMapper;
import java.time.Instant;
import java.util.List;
import org.junit.jupiter.api.Test;

class TranscriptReadyEventTests {

	@Test
	void serializesVersionedTenantSafeTimestampedContract() throws Exception {
		VideoTask task = new VideoTask(
				"task-1", "asset-1", "tenant-1", "owner-1", "demo.mp4",
				"secret/storage/path.mp4", "md5", "trace-1");
		task.setTranscriptResult(new TranscriptResult(
				"first second",
				List.of(
						new TranscriptResult.Segment("segment-0", 0, 0, 1200, "speaker-1", "first"),
						new TranscriptResult.Segment("segment-1", 1, 1200, 2500, null, "second")),
				"zh",
				2500L));

		var json = JsonMapper.builder().findAndAddModules().build().readTree(
				JsonMapper.builder().findAndAddModules().build().writeValueAsString(
						TranscriptReadyEvent.from(task, Instant.parse("2026-08-29T10:00:00Z"))));

		assertThat(json.path("event_id").asText()).isEqualTo("transcript:task-1:v1");
		assertThat(json.path("event_type").asText()).isEqualTo("transcript.ready.v1");
		assertThat(json.path("tenant_id").asText()).isEqualTo("tenant-1");
		assertThat(json.path("owner_id").asText()).isEqualTo("owner-1");
		assertThat(json.path("data").path("asset_id").asText()).isEqualTo("asset-1");
		assertThat(json.path("data").path("segments").get(1).path("start_ms").asLong()).isEqualTo(1200);
		assertThat(json.toString()).doesNotContain("secret/storage", "storage_path", "contentMd5");
	}
}
