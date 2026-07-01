package com.example.videoplatform.workflow;

import static org.assertj.core.api.Assertions.assertThat;
import static org.mockito.Mockito.inOrder;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.when;

import com.example.videoplatform.summary.SummaryService;
import com.example.videoplatform.transcript.TranscriptService;
import ch.qos.logback.classic.Level;
import ch.qos.logback.classic.Logger;
import org.junit.jupiter.api.Test;
import org.mockito.ArgumentCaptor;
import org.mockito.InOrder;
import org.slf4j.LoggerFactory;

class WorkflowProcessorTests {

	private final VideoTaskService videoTaskService = org.mockito.Mockito.mock(VideoTaskService.class);
	private final TranscriptService transcriptService = org.mockito.Mockito.mock(TranscriptService.class);
	private final SummaryService summaryService = org.mockito.Mockito.mock(SummaryService.class);
	private final WorkflowProcessor processor = new WorkflowProcessor(videoTaskService, transcriptService, summaryService);

	@Test
	void completesTaskThroughShortTransactionStages() {
		VideoTask task = new VideoTask("task-1", "video-1", "user-1", "demo.mp4", "storage/demo.mp4");
		when(videoTaskService.requireTask("task-1")).thenReturn(task);
		when(transcriptService.extract("storage/demo.mp4", "demo.mp4")).thenReturn("transcript");
		when(summaryService.summarize("transcript")).thenReturn("summary");

		processor.processAsync("task-1");

		// 每个阶段独立提交，且顺序必须是 状态推进 → 外部调用 → 落库
		InOrder inOrder = inOrder(videoTaskService, transcriptService, summaryService);
		inOrder.verify(videoTaskService).updateStatus("task-1", VideoTask.TaskStatus.TRANSCRIBING);
		inOrder.verify(transcriptService).extract("storage/demo.mp4", "demo.mp4");
		inOrder.verify(videoTaskService).completeTranscript("task-1", "transcript");
		inOrder.verify(summaryService).summarize("transcript");
		inOrder.verify(videoTaskService).completeSummary("task-1", "summary");
	}

	@Test
	void marksFailedAndTruncatesLongErrorMessage() {
		runWithWorkflowProcessorLogLevel(Level.OFF, () -> {
		VideoTask task = new VideoTask("task-1", "video-1", "user-1", "demo.mp4", "storage/demo.mp4");
		String longMessage = "x".repeat(2100);
		when(videoTaskService.requireTask("task-1")).thenReturn(task);
		when(transcriptService.extract("storage/demo.mp4", "demo.mp4")).thenThrow(new IllegalStateException(longMessage));

		processor.processAsync("task-1");

		ArgumentCaptor<String> messageCaptor = ArgumentCaptor.forClass(String.class);
		verify(videoTaskService).markFailed(org.mockito.ArgumentMatchers.eq("task-1"), messageCaptor.capture());
		assertThat(messageCaptor.getValue())
				.hasSize(2015)
				.endsWith("... [truncated]");
		});
	}

	@Test
	void persistsFailedTaskWhenSummaryFails() {
		runWithWorkflowProcessorLogLevel(Level.OFF, () -> {
		VideoTask task = new VideoTask("task-1", "video-1", "user-1", "demo.mp4", "storage/demo.mp4");
		when(videoTaskService.requireTask("task-1")).thenReturn(task);
		when(transcriptService.extract("storage/demo.mp4", "demo.mp4")).thenReturn("transcript");
		when(summaryService.summarize("transcript")).thenThrow(new IllegalStateException("summary failed"));

		processor.processAsync("task-1");

		verify(videoTaskService).completeTranscript("task-1", "transcript");
		verify(videoTaskService).markFailed("task-1", "summary failed");
		});
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
}
