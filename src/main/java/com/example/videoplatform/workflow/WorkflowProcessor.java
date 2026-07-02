package com.example.videoplatform.workflow;

import com.example.videoplatform.summary.SummaryService;
import com.example.videoplatform.transcript.TranscriptService;
import java.util.Optional;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.scheduling.annotation.Async;
import org.springframework.stereotype.Component;

@Component
public class WorkflowProcessor {

	private static final Logger log = LoggerFactory.getLogger(WorkflowProcessor.class);
	private static final int MAX_ERROR_MESSAGE_LENGTH = 2000;
	private static final String ASSET_LOCK_KEY = "lock:asset:%s";

	private final VideoTaskService videoTaskService;
	private final MediaAssetService mediaAssetService;
	private final DistributedLockService lockService;
	private final TranscriptService transcriptService;
	private final SummaryService summaryService;

	public WorkflowProcessor(VideoTaskService videoTaskService, MediaAssetService mediaAssetService,
			DistributedLockService lockService, TranscriptService transcriptService,
			SummaryService summaryService) {
		this.videoTaskService = videoTaskService;
		this.mediaAssetService = mediaAssetService;
		this.lockService = lockService;
		this.transcriptService = transcriptService;
		this.summaryService = summaryService;
	}

	/**
	 * 异步执行工作流。注意：不能在同一类中做内部调用（@Async 走代理）。
	 *
	 * <p>本方法<strong>不</strong>加 {@code @Transactional}。转写/摘要涉及 FFmpeg 与两次
	 * HTTP 调用，耗时可达数分钟；用一个大事务包裹会在整个外部 I/O 期间独占数据库连接，高并发下
	 * 迅速耗尽连接池，同时中间状态在提交前对前端轮询不可见。改为每阶段一个短事务，各自独立提交。
	 *
	 * <p>处理策略（内容级去重 + 幂等 + 单飞）：
	 * <ol>
	 *   <li><b>去重命中</b>：资产已 READY → 直接复用结果，秒完成，省去分钟级重复处理。</li>
	 *   <li><b>幂等占位</b>：仅从 QUEUED 抢占成功者继续，防 MQ 重复投递重复执行。</li>
	 *   <li><b>看门狗单飞</b>：对同一内容抢 {@code lock:asset:{md5}}（Redisson 看门狗横跨长处理），
	 *       赢家处理一次并 fan-out 完成所有同内容任务；抢锁失败者直接返回，由赢家完成。</li>
	 * </ol>
	 */
	@Async
	public void processAsync(String taskId) {
		log.info("Processing video task {}", taskId);
		VideoTask task = videoTaskService.requireTask(taskId);
		if (task.getStatus() == VideoTask.TaskStatus.COMPLETED) {
			log.info("Task {} already completed, skip", taskId);
			return;
		}

		String md5 = task.getContentMd5();

		// 1) 去重命中：同内容已处理过，直接复用结果
		if (md5 != null && !md5.isBlank()) {
			Optional<MediaAsset> ready = readyAsset(md5);
			if (ready.isPresent()) {
				log.info("Content {} already processed, reusing result for task {}", md5, taskId);
				videoTaskService.completeFromAsset(taskId, ready.get().getTranscript(), ready.get().getSummary());
				return;
			}
		}

		// 2) 幂等占位：只有从 QUEUED 抢占成功的 worker 继续
		if (!videoTaskService.claimForProcessing(taskId)) {
			log.info("Task {} already claimed/processed by another delivery, skip", taskId);
			return;
		}

		// 3) 无内容指纹（如单文件上传）→ 退化为仅处理本任务，不参与去重/单飞
		if (md5 == null || md5.isBlank()) {
			processStandalone(taskId, task);
			return;
		}

		// 4) 内容级单飞：抢内容锁的赢家处理一次并 fan-out
		processWithSingleFlight(taskId, task, md5);
	}

	private void processWithSingleFlight(String taskId, VideoTask task, String md5) {
		String lockKey = String.format(ASSET_LOCK_KEY, md5);
		if (!lockService.tryLockWithWatchdog(lockKey)) {
			// 别的 worker 正在处理同一内容；本任务已占位，交由赢家 fan-out 完成，避免重复处理与占用线程。
			log.info("Content {} is being processed by another worker; task {} will be completed by the winner",
					md5, taskId);
			return;
		}
		try {
			// double-check：抢锁期间赢家可能刚写好结果
			Optional<MediaAsset> ready = readyAsset(md5);
			if (ready.isPresent()) {
				videoTaskService.completeFromAsset(taskId, ready.get().getTranscript(), ready.get().getSummary());
				return;
			}

			mediaAssetService.markProcessing(md5, task.getStoragePath());

			String transcript = transcriptService.extract(task.getStoragePath(), task.getFileName());
			String summary = summaryService.summarize(transcript);

			mediaAssetService.markReady(md5, transcript, summary);
			int completed = videoTaskService.completeAllByContentMd5(md5, transcript, summary);
			log.info("Content {} processed; fanned out to {} task(s)", md5, completed);
		} catch (Exception exception) {
			log.warn("Video task {} (content {}) failed: {}", taskId, md5, exception.getMessage(), exception);
			String message = truncate(exception.getMessage());
			mediaAssetService.markFailed(md5, message);
			videoTaskService.failAllByContentMd5(md5, message);
		} finally {
			lockService.unlock(lockKey);
		}
	}

	private void processStandalone(String taskId, VideoTask task) {
		try {
			String transcript = transcriptService.extract(task.getStoragePath(), task.getFileName());
			videoTaskService.completeTranscript(taskId, transcript);

			String summary = summaryService.summarize(transcript);
			videoTaskService.completeSummary(taskId, summary);
			log.info("Video task {} completed", taskId);
		} catch (Exception exception) {
			log.warn("Video task {} failed: {}", taskId, exception.getMessage(), exception);
			videoTaskService.markFailed(taskId, truncate(exception.getMessage()));
		}
	}

	private Optional<MediaAsset> readyAsset(String md5) {
		return mediaAssetService.find(md5)
				.filter(asset -> asset.getStatus() == MediaAsset.AssetStatus.READY);
	}

	private static String truncate(String message) {
		if (message != null && message.length() > MAX_ERROR_MESSAGE_LENGTH) {
			return message.substring(0, MAX_ERROR_MESSAGE_LENGTH) + "... [truncated]";
		}
		return message;
	}
}
