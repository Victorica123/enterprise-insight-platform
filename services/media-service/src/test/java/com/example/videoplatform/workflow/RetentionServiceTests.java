package com.example.videoplatform.workflow;

import static org.assertj.core.api.Assertions.assertThat;
import static org.mockito.ArgumentMatchers.any;
import static org.mockito.ArgumentMatchers.anyList;
import static org.mockito.Mockito.mock;
import static org.mockito.Mockito.never;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.when;

import com.example.videoplatform.config.AppProperties;
import io.micrometer.core.instrument.simple.SimpleMeterRegistry;
import java.util.List;
import org.junit.jupiter.api.Test;

class RetentionServiceTests {

	@Test
	void clearsDatabasePointersAndQueuesDurableObjectCleanup() {
		AppProperties properties = new AppProperties();
		properties.getRetention().setEnabled(true);
		VideoTaskRepository tasks = mock(VideoTaskRepository.class);
		MediaAssetRepository assets = mock(MediaAssetRepository.class);
		MediaCleanupJobRepository cleanup = mock(MediaCleanupJobRepository.class);
		VideoTask task = new VideoTask("task-1", "video-1", "user-1", "old.mp4", "s3://bucket/old.mp4");
		task.setTranscript("old transcript");
		task.setSummary("summary retained");
		task.setStatus(VideoTask.TaskStatus.COMPLETED);
		MediaAsset asset = new MediaAsset("md5-old", "s3://bucket/old.mp4");
		asset.markReady("old transcript", "summary retained");
		when(tasks.findMediaRetentionCandidates(anyList(), any(), any())).thenReturn(List.of(task));
		when(tasks.findTranscriptRetentionCandidates(anyList(), any(), any())).thenReturn(List.of(task));
		when(tasks.existsByStoragePath("s3://bucket/old.mp4")).thenReturn(false);
		when(assets.findByStoragePath("s3://bucket/old.mp4")).thenReturn(List.of(asset));
		when(assets.findTranscriptRetentionCandidates(any(), any())).thenReturn(List.of(asset));
		RetentionService service = new RetentionService(
				properties, tasks, assets, cleanup, new SimpleMeterRegistry());

		RetentionService.RetentionBatch result = service.enforceRetention();

		assertThat(result.mediaTasks()).isEqualTo(1);
		assertThat(task.getStoragePath()).isNull();
		assertThat(task.getTranscript()).isNull();
		assertThat(task.getSummary()).isEqualTo("summary retained");
		assertThat(asset.getStoragePath()).isNull();
		assertThat(asset.getStatus()).isEqualTo(MediaAsset.AssetStatus.RETENTION_EXPIRED);
		assertThat(asset.getSummary()).isEqualTo("summary retained");
		verify(cleanup).save(any(MediaCleanupJob.class));
	}

	@Test
	void doesNotDeleteDeduplicatedObjectWhileAnotherTaskStillReferencesIt() {
		AppProperties properties = new AppProperties();
		properties.getRetention().setEnabled(true);
		VideoTaskRepository tasks = mock(VideoTaskRepository.class);
		MediaAssetRepository assets = mock(MediaAssetRepository.class);
		MediaCleanupJobRepository cleanup = mock(MediaCleanupJobRepository.class);
		String path = "s3://bucket/shared.mp4";
		VideoTask expiredTask = new VideoTask("task-old", "video-old", "user-1", "old.mp4", path);
		expiredTask.setStatus(VideoTask.TaskStatus.COMPLETED);
		when(tasks.findMediaRetentionCandidates(anyList(), any(), any())).thenReturn(List.of(expiredTask));
		when(tasks.findTranscriptRetentionCandidates(anyList(), any(), any())).thenReturn(List.of());
		when(tasks.existsByStoragePath(path)).thenReturn(true);
		when(assets.findTranscriptRetentionCandidates(any(), any())).thenReturn(List.of());
		RetentionService service = new RetentionService(
				properties, tasks, assets, cleanup, new SimpleMeterRegistry());

		RetentionService.RetentionBatch result = service.enforceRetention();

		assertThat(result.mediaTasks()).isEqualTo(1);
		assertThat(expiredTask.getStoragePath()).isNull();
		verify(assets, never()).findByStoragePath(path);
		verify(cleanup, never()).save(any(MediaCleanupJob.class));
	}
}
