package com.example.videoplatform.workflow;

import com.example.videoplatform.media.MediaStorageService;
import com.example.videoplatform.workflow.TaskStageLog.Stage;
import com.example.videoplatform.summary.SummaryService;
import com.example.videoplatform.transcript.TranscriptResult;
import com.example.videoplatform.transcript.TranscriptService;
import io.micrometer.core.instrument.Timer;
import java.util.Optional;
import java.util.concurrent.ScheduledThreadPoolExecutor;
import java.util.concurrent.ScheduledFuture;
import java.util.concurrent.ThreadFactory;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicBoolean;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.scheduling.annotation.Async;
import org.springframework.stereotype.Component;

@Component
public class WorkflowProcessor {

	private static final Logger log = LoggerFactory.getLogger(WorkflowProcessor.class);
	private static final int MAX_ERROR_MESSAGE_LENGTH = 2000;
	private static final String ASSET_LOCK_KEY = "lock:asset:%s:%s";
	private static final ScheduledThreadPoolExecutor LEASE_HEARTBEAT_EXECUTOR = heartbeatExecutor();

	private final VideoTaskService videoTaskService;
	private final MediaAssetService mediaAssetService;
	private final DistributedLockService lockService;
	private final TranscriptService transcriptService;
	private final SummaryService summaryService;
	private final WorkflowMetrics metrics;
	private final MediaStorageService mediaStorageService;
	private final ModelEgressPolicy modelEgressPolicy;
	private final TaskStageLogService stageLogs;

	public WorkflowProcessor(VideoTaskService videoTaskService, MediaAssetService mediaAssetService,
			DistributedLockService lockService, TranscriptService transcriptService,
			SummaryService summaryService, WorkflowMetrics metrics, MediaStorageService mediaStorageService,
			ModelEgressPolicy modelEgressPolicy, TaskStageLogService stageLogs) {
		this.videoTaskService = videoTaskService;
		this.mediaAssetService = mediaAssetService;
		this.lockService = lockService;
		this.transcriptService = transcriptService;
		this.summaryService = summaryService;
		this.metrics = metrics;
		this.mediaStorageService = mediaStorageService;
		this.modelEgressPolicy = modelEgressPolicy;
		this.stageLogs = stageLogs;
	}

	/**
	 * Async execution entry point.  The task lease is renewed while external
	 * FFmpeg/Whisper/LLM calls are in progress so the reaper cannot duplicate a
	 * live worker; the lease token also detects a reaper takeover.
	 */
	@Async
	public void processAsync(String taskId) {
		process(taskId);
	}

	/** Synchronous entry point used by MQ consumers to provide natural backpressure. */
	public void process(String taskId) {
		log.info("Processing video task {}", taskId);
		VideoTask task = videoTaskService.requireTask(taskId);
		if (task.getStatus() == VideoTask.TaskStatus.COMPLETED) {
			log.info("Task {} already completed, skip", taskId);
			metrics.incrementSkip("already_completed");
			return;
		}

		TaskStageObserver stages = new TaskStageObserver(stageLogs, taskId);
		String tenantId = task.getTenantId();
		String md5 = task.getContentMd5();

		// A READY result is selected only from the same tenant scope.
		if (md5 != null && !md5.isBlank()) {
			Optional<MediaAsset> ready = readyAsset(tenantId, md5);
			if (ready.isPresent()) {
				log.info("Content {} already processed in tenant {}, reusing result for task {}",
						md5, tenantId, taskId);
				Timer.Sample sample = metrics.startProcessing();
				stages.run(Stage.RESULT_REUSE, () -> {
					videoTaskService.completeFromAsset(taskId, ready.get().getTranscriptResult(), ready.get().getSummary());
					return null;
				});
				metrics.stopProcessing(sample, "dedup", "completed");
				metrics.recordEndToEnd(task.getCreatedAt(), "completed");
				return;
			}
		}

		Optional<String> lease = videoTaskService.claimForProcessingWithLease(taskId);
		if (lease.isEmpty()) {
			log.info("Task {} already claimed/processed by another delivery, skip", taskId);
			metrics.incrementSkip("claim_lost");
			return;
		}

		try (LeaseHeartbeat heartbeat = LeaseHeartbeat.start(
				taskId, lease.get(), videoTaskService, videoTaskService.leaseHeartbeatIntervalMillis())) {
			if (md5 == null || md5.isBlank()) {
				processStandalone(taskId, task, heartbeat, stages);
				return;
			}
			processWithSingleFlight(taskId, task, tenantId, md5, heartbeat, stages);
		}
	}

	private void processWithSingleFlight(
			String taskId, VideoTask task, String tenantId, String md5, LeaseHeartbeat heartbeat, TaskStageObserver stages) {
		String lockKey = String.format(ASSET_LOCK_KEY, tenantId, md5);
		if (!lockService.tryLockWithWatchdog(lockKey)) {
			log.info("Content {} is being processed by another worker in tenant {}; task {} will be completed by the winner",
					md5, tenantId, taskId);
			metrics.incrementSkip("single_flight_loser");
			return;
		}
		Timer.Sample sample = metrics.startProcessing();
		try {
			// Double-check after acquiring the tenant-scoped content lock.
			Optional<MediaAsset> ready = readyAsset(tenantId, md5);
			if (ready.isPresent()) {
				heartbeat.ensureOwned();
				stages.run(Stage.RESULT_REUSE, () -> {
					videoTaskService.completeFromAsset(taskId, ready.get().getTranscriptResult(), ready.get().getSummary());
					return null;
				});
				metrics.stopProcessing(sample, "dedup", "completed");
				metrics.recordEndToEnd(task.getCreatedAt(), "completed");
				return;
			}

			heartbeat.ensureOwned();
			mediaAssetService.markProcessing(tenantId, md5, task.getStoragePath());

			TranscriptResult transcript;
			modelEgressPolicy.requireTranscriptAllowed(tenantId);
			try (MediaStorageService.ResolvedMedia media = stages.run(Stage.STORAGE_RESOLVE,
					() -> mediaStorageService.resolveForProcessing(task.getStoragePath()))) {
				transcript = transcriptService.extract(media.localPath().toString(), task.getFileName(), stages);
			}
			heartbeat.ensureOwned();
			modelEgressPolicy.requireSummaryAllowed(tenantId);
			String summary = stages.run(Stage.SUMMARY, () -> summaryService.summarize(transcript.text()));
			heartbeat.ensureOwned();

			stages.run(Stage.RESULT_COMMIT, () -> {
				mediaAssetService.markReady(tenantId, md5, transcript, summary);
				if (!videoTaskService.completeAllByContentMd5(
						tenantId, md5, transcript, summary, taskId, heartbeat.leaseId())) {
					throw new LeaseLostException();
				}
				return null;
			});
			log.info("Content {} in tenant {} processed; fan-out committed", md5, tenantId);
			metrics.stopProcessing(sample, "single_flight", "completed");
			metrics.recordEndToEnd(task.getCreatedAt(), "completed");
		} catch (LeaseLostException exception) {
			log.warn("Task {} lost its processing lease; leaving it for the reaper", taskId);
			metrics.stopProcessing(sample, "single_flight", "lease_lost");
		} catch (Exception exception) {
			try {
				heartbeat.ensureOwned();
			} catch (LeaseLostException lost) {
				log.warn("Task {} lost its processing lease while handling a failure", taskId);
				metrics.stopProcessing(sample, "single_flight", "lease_lost");
				return;
			}
			log.warn("Video task {} (tenant {}, content {}) failed: {}", taskId, tenantId, md5,
				exception.getMessage(), exception);
			String message = truncate(exception.getMessage());
			if (!videoTaskService.failAllByContentMd5(
					tenantId, md5, message, taskId, heartbeat.leaseId())) {
				log.warn("Task {} lost its processing lease before failure could be persisted", taskId);
				metrics.stopProcessing(sample, "single_flight", "lease_lost");
				return;
			}
			mediaAssetService.markFailed(tenantId, md5, message);
			metrics.stopProcessing(sample, "single_flight", "failed");
		} finally {
			lockService.unlock(lockKey);
		}
	}

	private void processStandalone(String taskId, VideoTask task, LeaseHeartbeat heartbeat, TaskStageObserver stages) {
		Timer.Sample sample = metrics.startProcessing();
		try {
			TranscriptResult transcript;
			modelEgressPolicy.requireTranscriptAllowed(task.getTenantId());
			try (MediaStorageService.ResolvedMedia media = stages.run(Stage.STORAGE_RESOLVE,
					() -> mediaStorageService.resolveForProcessing(task.getStoragePath()))) {
				transcript = transcriptService.extract(media.localPath().toString(), task.getFileName(), stages);
			}
			heartbeat.ensureOwned();
			if (!videoTaskService.completeTranscript(taskId, transcript, heartbeat.leaseId())) {
				throw new LeaseLostException();
			}

			modelEgressPolicy.requireSummaryAllowed(task.getTenantId());
			String summary = stages.run(Stage.SUMMARY, () -> summaryService.summarize(transcript.text()));
			heartbeat.ensureOwned();
			stages.run(Stage.RESULT_COMMIT, () -> {
				if (!videoTaskService.completeSummary(taskId, summary, heartbeat.leaseId())) {
					throw new LeaseLostException();
				}
				return null;
			});
			log.info("Video task {} completed", taskId);
			metrics.stopProcessing(sample, "standalone", "completed");
			metrics.recordEndToEnd(task.getCreatedAt(), "completed");
		} catch (LeaseLostException exception) {
			log.warn("Task {} lost its processing lease; leaving it for the reaper", taskId);
			metrics.stopProcessing(sample, "standalone", "lease_lost");
		} catch (Exception exception) {
			try {
				heartbeat.ensureOwned();
			} catch (LeaseLostException lost) {
				log.warn("Task {} lost its processing lease while handling a failure", taskId);
				metrics.stopProcessing(sample, "standalone", "lease_lost");
				return;
			}
			log.warn("Video task {} failed: {}", taskId, exception.getMessage(), exception);
			if (!videoTaskService.markFailed(taskId, truncate(exception.getMessage()), heartbeat.leaseId())) {
				log.warn("Task {} lost its processing lease before failure could be persisted", taskId);
				metrics.stopProcessing(sample, "standalone", "lease_lost");
				return;
			}
			metrics.stopProcessing(sample, "standalone", "failed");
		}
	}

	private Optional<MediaAsset> readyAsset(String tenantId, String md5) {
		return mediaAssetService.find(tenantId, md5)
				.filter(asset -> asset.getStatus() == MediaAsset.AssetStatus.READY);
	}

	private static ThreadFactory daemonThreadFactory() {
		return runnable -> {
			Thread thread = new Thread(runnable, "video-task-lease-heartbeat");
			thread.setDaemon(true);
			return thread;
		};
	}

	private static ScheduledThreadPoolExecutor heartbeatExecutor() {
		ScheduledThreadPoolExecutor executor = new ScheduledThreadPoolExecutor(2, daemonThreadFactory());
		executor.setRemoveOnCancelPolicy(true);
		executor.setExecuteExistingDelayedTasksAfterShutdownPolicy(false);
		executor.setContinueExistingPeriodicTasksAfterShutdownPolicy(false);
		return executor;
	}

	static boolean removesCancelledHeartbeats() {
		return LEASE_HEARTBEAT_EXECUTOR.getRemoveOnCancelPolicy();
	}

	private static String truncate(String message) {
		if (message != null && message.length() > MAX_ERROR_MESSAGE_LENGTH) {
			return message.substring(0, MAX_ERROR_MESSAGE_LENGTH) + "... [truncated]";
		}
		return message;
	}

	private static final class LeaseHeartbeat implements AutoCloseable {
		private final VideoTaskService taskService;
		private final String taskId;
		private final String leaseId;
		private final AtomicBoolean lost = new AtomicBoolean();
		private final ScheduledFuture<?> future;

		private LeaseHeartbeat(VideoTaskService taskService, String taskId, String leaseId, long intervalMillis) {
			this.taskService = taskService;
			this.taskId = taskId;
			this.leaseId = leaseId;
			this.future = LEASE_HEARTBEAT_EXECUTOR.scheduleAtFixedRate(this::renew, intervalMillis,
					intervalMillis, TimeUnit.MILLISECONDS);
		}

		static LeaseHeartbeat start(String taskId, String leaseId, VideoTaskService taskService, long intervalMillis) {
			return new LeaseHeartbeat(taskService, taskId, leaseId, Math.max(1000L, intervalMillis));
		}

		private void renew() {
			try {
				if (!taskService.renewProcessingLease(taskId, leaseId)) {
					lost.set(true);
				}
			} catch (RuntimeException exception) {
				lost.set(true);
				// The worker will stop committing after the next boundary check;
				// the reaper remains the recovery authority.
				log.warn("Unable to renew lease for task {}: {}", taskId, exception.getMessage());
			}
		}

		void ensureOwned() {
			if (lost.get()) {
				throw new LeaseLostException();
			}
		}

		String leaseId() {
			return leaseId;
		}

		@Override
		public void close() {
			future.cancel(false);
		}
	}

	private static final class LeaseLostException extends RuntimeException {
		private static final long serialVersionUID = 1L;
	}
}
