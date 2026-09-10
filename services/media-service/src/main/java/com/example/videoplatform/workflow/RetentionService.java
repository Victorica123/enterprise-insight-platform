package com.example.videoplatform.workflow;

import com.example.videoplatform.config.AppProperties;
import io.micrometer.core.instrument.MeterRegistry;
import java.time.Instant;
import java.time.temporal.ChronoUnit;
import java.util.LinkedHashSet;
import java.util.List;
import java.util.Set;
import org.springframework.data.domain.PageRequest;
import org.springframework.scheduling.annotation.Scheduled;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

/** Applies the approved 30/180 day media and transcript retention windows in bounded batches. */
@Service
public class RetentionService {

	private static final List<VideoTask.TaskStatus> TERMINAL = List.of(
			VideoTask.TaskStatus.COMPLETED, VideoTask.TaskStatus.FAILED);

	private final AppProperties properties;
	private final VideoTaskRepository taskRepository;
	private final MediaAssetRepository assetRepository;
	private final MediaCleanupJobRepository cleanupJobRepository;
	private final MeterRegistry meterRegistry;

	public RetentionService(AppProperties properties, VideoTaskRepository taskRepository,
			MediaAssetRepository assetRepository, MediaCleanupJobRepository cleanupJobRepository,
			MeterRegistry meterRegistry) {
		this.properties = properties;
		this.taskRepository = taskRepository;
		this.assetRepository = assetRepository;
		this.cleanupJobRepository = cleanupJobRepository;
		this.meterRegistry = meterRegistry;
	}

	@Scheduled(fixedDelayString = "${app.retention.scan-interval-ms:3600000}",
			initialDelayString = "${app.retention.initial-delay-ms:60000}")
	@Transactional
	public RetentionBatch enforceRetention() {
		if (!properties.getRetention().isEnabled()) {
			return new RetentionBatch(0, 0, 0);
		}
		validateDays();
		int size = Math.max(1, Math.min(1000, properties.getRetention().getBatchSize()));
		PageRequest page = PageRequest.of(0, size);
		Instant now = Instant.now();

		List<VideoTask> mediaCandidates = taskRepository.findMediaRetentionCandidates(
				TERMINAL, now.minus(properties.getRetention().getMediaDays(), ChronoUnit.DAYS), page);
		Set<String> storagePaths = new LinkedHashSet<>();
		for (VideoTask task : mediaCandidates) {
			if (task.getStoragePath() != null && !task.getStoragePath().isBlank()) {
				storagePaths.add(task.getStoragePath());
				task.clearStoredMedia();
			}
		}
		taskRepository.flush();
		for (String path : storagePaths) {
			if (!taskRepository.existsByStoragePath(path)) {
				assetRepository.findByStoragePath(path).forEach(MediaAsset::clearStoredMedia);
				cleanupJobRepository.save(new MediaCleanupJob(path));
			}
		}

		List<VideoTask> transcriptCandidates = taskRepository.findTranscriptRetentionCandidates(
				TERMINAL, now.minus(properties.getRetention().getTranscriptDays(), ChronoUnit.DAYS), page);
		transcriptCandidates.forEach(VideoTask::clearTranscriptData);
		List<MediaAsset> assetCandidates = assetRepository.findTranscriptRetentionCandidates(
				now.minus(properties.getRetention().getTranscriptDays(), ChronoUnit.DAYS), page);
		assetCandidates.forEach(MediaAsset::expireTranscriptData);

		increment("media", mediaCandidates.size());
		increment("transcript_task", transcriptCandidates.size());
		increment("transcript_asset", assetCandidates.size());
		return new RetentionBatch(mediaCandidates.size(), transcriptCandidates.size(), assetCandidates.size());
	}

	private void validateDays() {
		if (properties.getRetention().getMediaDays() <= 0
				|| properties.getRetention().getTranscriptDays() <= 0
				|| properties.getRetention().getAuditDays() <= 0) {
			throw new IllegalStateException("Retention days must all be positive.");
		}
	}

	private void increment(String dataClass, int count) {
		if (count > 0) {
			meterRegistry.counter("video.retention.records", "data_class", dataClass).increment(count);
		}
	}

	public record RetentionBatch(int mediaTasks, int transcriptTasks, int transcriptAssets) {
	}
}
