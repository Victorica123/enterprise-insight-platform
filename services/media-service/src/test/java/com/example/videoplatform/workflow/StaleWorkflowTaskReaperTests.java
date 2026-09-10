package com.example.videoplatform.workflow;

import static org.mockito.Mockito.never;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.when;

import com.example.videoplatform.config.AppProperties;
import io.micrometer.core.instrument.simple.SimpleMeterRegistry;
import java.time.Duration;
import java.util.List;
import org.junit.jupiter.api.Test;
import org.mockito.ArgumentCaptor;

class StaleWorkflowTaskReaperTests {

	private final VideoTaskService videoTaskService = org.mockito.Mockito.mock(VideoTaskService.class);
	private final AppProperties appProperties = new AppProperties();
	private final SimpleMeterRegistry meterRegistry = new SimpleMeterRegistry();
	private final WorkflowMetrics workflowMetrics = new WorkflowMetrics(meterRegistry);
	private final StaleWorkflowTaskReaper reaper = new StaleWorkflowTaskReaper(
			videoTaskService, appProperties, workflowMetrics);

	@Test
	void requeueStaleTasksRecordsDurablyRequeuedTaskIds() {
		appProperties.getWorkflow().setStaleTaskTimeout(Duration.ofMinutes(30));
		when(videoTaskService.requeueStaleTasks(org.mockito.ArgumentMatchers.any()))
				.thenReturn(List.of("task-1", "task-2"));

		reaper.requeueStaleTasks();

		ArgumentCaptor<java.time.Instant> cutoffCaptor = ArgumentCaptor.forClass(java.time.Instant.class);
		verify(videoTaskService).requeueStaleTasks(cutoffCaptor.capture());
		org.assertj.core.api.Assertions.assertThat(meterRegistry.counter("video.task.requeued", "source", "reaper").count())
				.isEqualTo(2);
	}

	@Test
	void requeueStaleTasksSkipsWhenTimeoutIsInvalid() {
		appProperties.getWorkflow().setStaleTaskTimeout(Duration.ZERO);

		reaper.requeueStaleTasks();

		verify(videoTaskService, never()).requeueStaleTasks(org.mockito.ArgumentMatchers.any());
	}
}
