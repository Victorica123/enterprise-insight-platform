package com.example.videoplatform.workflow;

import com.example.videoplatform.summary.SummaryService;
import com.example.videoplatform.transcript.TranscriptService;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.scheduling.annotation.Async;
import org.springframework.stereotype.Component;

@Component
public class WorkflowProcessor {

	private static final Logger log = LoggerFactory.getLogger(WorkflowProcessor.class);
	private static final int MAX_ERROR_MESSAGE_LENGTH = 2000;

	private final VideoTaskService videoTaskService;
	private final TranscriptService transcriptService;
	private final SummaryService summaryService;

	public WorkflowProcessor(VideoTaskService videoTaskService, TranscriptService transcriptService,
			SummaryService summaryService) {
		this.videoTaskService = videoTaskService;
		this.transcriptService = transcriptService;
		this.summaryService = summaryService;
	}

	/**
	 * 异步执行工作流。注意：不能在同一类中做内部调用（@Async 走代理）。
	 *
	 * <p>本方法<strong>不</strong>加 {@code @Transactional}。转写/摘要涉及 FFmpeg 与两次
	 * HTTP 调用，耗时可达数分钟；若用一个大事务包裹，会在整个外部 I/O 期间独占一条数据库连接，
	 * 高并发下迅速耗尽连接池，同时 TRANSCRIBING / SUMMARIZING 等中间状态在事务提交前对
	 * 前端轮询不可见。改为每个阶段一个短事务，各自独立提交。
	 */
	@Async
	public void processAsync(String taskId) {
		log.info("Processing video task {}", taskId);
		VideoTask task = videoTaskService.requireTask(taskId);
		try {
			videoTaskService.updateStatus(taskId, VideoTask.TaskStatus.TRANSCRIBING);

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

	private static String truncate(String message) {
		if (message != null && message.length() > MAX_ERROR_MESSAGE_LENGTH) {
			return message.substring(0, MAX_ERROR_MESSAGE_LENGTH) + "... [truncated]";
		}
		return message;
	}
}
