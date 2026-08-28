package com.example.videoplatform.workflow;

import static org.assertj.core.api.Assertions.assertThat;
import static org.mockito.ArgumentMatchers.anyString;
import static org.mockito.Mockito.inOrder;
import static org.mockito.Mockito.never;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.verifyNoInteractions;
import static org.mockito.Mockito.when;

import com.example.videoplatform.media.MediaStorageService;
import com.example.videoplatform.summary.SummaryService;
import com.example.videoplatform.transcript.TranscriptService;
import com.example.videoplatform.transcript.TranscriptResult;
import ch.qos.logback.classic.Level;
import ch.qos.logback.classic.Logger;
import io.micrometer.core.instrument.simple.SimpleMeterRegistry;
import java.nio.file.Path;
import java.util.Optional;
import org.junit.jupiter.api.Test;
import org.mockito.ArgumentCaptor;
import org.mockito.InOrder;
import org.slf4j.LoggerFactory;

class WorkflowProcessorTests {

	private final VideoTaskService videoTaskService = org.mockito.Mockito.mock(VideoTaskService.class);
	private final MediaAssetService mediaAssetService = org.mockito.Mockito.mock(MediaAssetService.class);
	private final DistributedLockService lockService = org.mockito.Mockito.mock(DistributedLockService.class);
	private final TranscriptService transcriptService = org.mockito.Mockito.mock(TranscriptService.class);
	private final SummaryService summaryService = org.mockito.Mockito.mock(SummaryService.class);
	private final MediaStorageService mediaStorageService = org.mockito.Mockito.mock(MediaStorageService.class);
	private final SimpleMeterRegistry meterRegistry = new SimpleMeterRegistry();
	private final WorkflowMetrics workflowMetrics = new WorkflowMetrics(meterRegistry);
	private final WorkflowProcessor processor = new WorkflowProcessor(
			videoTaskService, mediaAssetService, lockService, transcriptService, summaryService, workflowMetrics,
			mediaStorageService);
	private static final String RESOLVED_STORAGE_PATH = Path.of("storage", "demo.mp4").toString();
	private static final TranscriptResult TRANSCRIPT = TranscriptResult.fromPlainText("transcript");

	private static VideoTask task(String contentMd5) {
		return new VideoTask("task-1", "video-1", "user-1", "demo.mp4", "storage/demo.mp4", contentMd5);
	}

	@Test
	void standaloneTaskWithoutContentMd5RunsThroughShortTransactionStages() {
		when(videoTaskService.requireTask("task-1")).thenReturn(task(null));
		when(videoTaskService.claimForProcessing("task-1")).thenReturn(true);
		stubResolvedMedia();
		when(transcriptService.extract(RESOLVED_STORAGE_PATH, "demo.mp4")).thenReturn(TRANSCRIPT);
		when(summaryService.summarize("transcript")).thenReturn("summary");

		processor.processAsync("task-1");

		InOrder inOrder = inOrder(videoTaskService, transcriptService, summaryService);
		inOrder.verify(videoTaskService).claimForProcessing("task-1");
		inOrder.verify(transcriptService).extract(RESOLVED_STORAGE_PATH, "demo.mp4");
		inOrder.verify(videoTaskService).completeTranscript("task-1", TRANSCRIPT);
		inOrder.verify(summaryService).summarize("transcript");
		inOrder.verify(videoTaskService).completeSummary("task-1", "summary");
		verifyNoInteractions(lockService);
	}

	@Test
	void reusesReadyAssetWithoutReprocessing() {
		MediaAsset ready = new MediaAsset("md5-1", "storage/demo.mp4");
		ready.markReady("cached transcript", "cached summary");
		when(videoTaskService.requireTask("task-1")).thenReturn(task("md5-1"));
		when(mediaAssetService.find("md5-1")).thenReturn(Optional.of(ready));

		processor.processAsync("task-1");

		// 去重命中：直接复用，不抢占、不加锁、不跑 FFmpeg/Whisper/LLM
		verify(videoTaskService).completeFromAsset(
				"task-1", TranscriptResult.fromPlainText("cached transcript"), "cached summary");
		verify(videoTaskService, never()).claimForProcessing(anyString());
		verifyNoInteractions(lockService, transcriptService, summaryService);
	}

	@Test
	void singleFlightWinnerProcessesOnceAndFansOut() {
		when(videoTaskService.requireTask("task-1")).thenReturn(task("md5-1"));
		when(mediaAssetService.find("md5-1")).thenReturn(Optional.empty());
		when(videoTaskService.claimForProcessing("task-1")).thenReturn(true);
		when(lockService.tryLockWithWatchdog("lock:asset:md5-1")).thenReturn(true);
		stubResolvedMedia();
		when(transcriptService.extract(RESOLVED_STORAGE_PATH, "demo.mp4")).thenReturn(TRANSCRIPT);
		when(summaryService.summarize("transcript")).thenReturn("summary");

		processor.processAsync("task-1");

		InOrder inOrder = inOrder(lockService, mediaAssetService, videoTaskService);
		inOrder.verify(lockService).tryLockWithWatchdog("lock:asset:md5-1");
		inOrder.verify(mediaAssetService).markProcessing("md5-1", "storage/demo.mp4");
		inOrder.verify(mediaAssetService).markReady("md5-1", TRANSCRIPT, "summary");
		inOrder.verify(videoTaskService).completeAllByContentMd5("md5-1", TRANSCRIPT, "summary");
		inOrder.verify(lockService).unlock("lock:asset:md5-1");
	}

	@Test
	void singleFlightLoserSkipsProcessingAndLeavesCompletionToWinner() {
		when(videoTaskService.requireTask("task-1")).thenReturn(task("md5-1"));
		when(mediaAssetService.find("md5-1")).thenReturn(Optional.empty());
		when(videoTaskService.claimForProcessing("task-1")).thenReturn(true);
		when(lockService.tryLockWithWatchdog("lock:asset:md5-1")).thenReturn(false);

		processor.processAsync("task-1");

		// 抢锁失败者不处理、不释放锁（未持有），交由赢家 fan-out 完成
		verifyNoInteractions(transcriptService, summaryService);
		verify(mediaAssetService, never()).markProcessing(anyString(), anyString());
		verify(lockService, never()).unlock(anyString());
	}

	@Test
	void idempotentSkipWhenClaimFails() {
		when(videoTaskService.requireTask("task-1")).thenReturn(task(null));
		when(videoTaskService.claimForProcessing("task-1")).thenReturn(false);

		processor.processAsync("task-1");

		// 重复投递：抢占失败直接跳过，不重复处理
		verifyNoInteractions(transcriptService, summaryService, lockService);
	}

	@Test
	void skipsAlreadyCompletedTask() {
		VideoTask completed = task("md5-1");
		completed.setStatus(VideoTask.TaskStatus.COMPLETED);
		when(videoTaskService.requireTask("task-1")).thenReturn(completed);

		processor.processAsync("task-1");

		verifyNoInteractions(mediaAssetService, lockService, transcriptService, summaryService);
		verify(videoTaskService, never()).claimForProcessing(anyString());
	}

	@Test
	void singleFlightFailureMarksAssetAndTasksFailedWithTruncation() {
		runWithWorkflowProcessorLogLevel(Level.OFF, () -> {
			String longMessage = "x".repeat(2100);
			when(videoTaskService.requireTask("task-1")).thenReturn(task("md5-1"));
			when(mediaAssetService.find("md5-1")).thenReturn(Optional.empty());
			when(videoTaskService.claimForProcessing("task-1")).thenReturn(true);
			when(lockService.tryLockWithWatchdog("lock:asset:md5-1")).thenReturn(true);
			stubResolvedMedia();
			when(transcriptService.extract(RESOLVED_STORAGE_PATH, "demo.mp4"))
					.thenThrow(new IllegalStateException(longMessage));

			processor.processAsync("task-1");

			ArgumentCaptor<String> messageCaptor = ArgumentCaptor.forClass(String.class);
			verify(mediaAssetService).markFailed(org.mockito.ArgumentMatchers.eq("md5-1"), messageCaptor.capture());
			verify(videoTaskService).failAllByContentMd5(org.mockito.ArgumentMatchers.eq("md5-1"), anyString());
			verify(lockService).unlock("lock:asset:md5-1");
			assertThat(messageCaptor.getValue()).hasSize(2015).endsWith("... [truncated]");
		});
	}

	@Test
	void standaloneFailurePersistsFailedTask() {
		runWithWorkflowProcessorLogLevel(Level.OFF, () -> {
			when(videoTaskService.requireTask("task-1")).thenReturn(task(null));
			when(videoTaskService.claimForProcessing("task-1")).thenReturn(true);
			stubResolvedMedia();
			when(transcriptService.extract(RESOLVED_STORAGE_PATH, "demo.mp4")).thenReturn(TRANSCRIPT);
			when(summaryService.summarize("transcript")).thenThrow(new IllegalStateException("summary failed"));

			processor.processAsync("task-1");

			verify(videoTaskService).completeTranscript("task-1", TRANSCRIPT);
			verify(videoTaskService).markFailed("task-1", "summary failed");
		});
	}

	@Test
	void recordsProcessingAndEndToEndMetricsOnStandaloneCompletion() {
		when(videoTaskService.requireTask("task-1")).thenReturn(task(null));
		when(videoTaskService.claimForProcessing("task-1")).thenReturn(true);
		stubResolvedMedia();
		when(transcriptService.extract(RESOLVED_STORAGE_PATH, "demo.mp4")).thenReturn(TRANSCRIPT);
		when(summaryService.summarize("transcript")).thenReturn("summary");

		processor.processAsync("task-1");

		// 处理耗时按 path/result 打点；端到端耗时按 result 打点，供 Prometheus 聚合 P50/P99
		assertThat(meterRegistry.get("video.task.processing")
				.tags("path", "standalone", "result", "completed").timer().count()).isEqualTo(1L);
		assertThat(meterRegistry.get("video.task.e2e")
				.tags("result", "completed").timer().count()).isEqualTo(1L);
	}

	@Test
	void countsSkippedTasksByReason() {
		VideoTask completed = task("md5-1");
		completed.setStatus(VideoTask.TaskStatus.COMPLETED);
		when(videoTaskService.requireTask("task-1")).thenReturn(completed);

		processor.processAsync("task-1");

		// 去重/幂等/单飞省下的处理次数可量化：已完成任务被重复投递时计入 already_completed
		assertThat(meterRegistry.get("video.task.skipped")
				.tags("reason", "already_completed").counter().count()).isEqualTo(1.0);
	}

	private static void runWithWorkflowProcessorLogLevel(Level level, Runnable runnable) {
		Logger logger = (Logger) LoggerFactory.getLogger(WorkflowProcessor.class);
		Level originalLevel = logger.getLevel();
		logger.setLevel(level);
		try {
			runnable.run();
		} finally {
			logger.setLevel(originalLevel);
		}
	}

	private void stubResolvedMedia() {
		try {
			when(mediaStorageService.resolveForProcessing("storage/demo.mp4"))
					.thenReturn(new MediaStorageService.ResolvedMedia(Path.of("storage", "demo.mp4"), false));
		} catch (java.io.IOException e) {
			throw new IllegalStateException(e);
		}
	}
}
