package com.example.videoplatform.workflow;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;
import static org.mockito.ArgumentMatchers.eq;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.when;

import java.time.Instant;
import java.util.List;
import java.util.Optional;
import org.junit.jupiter.api.Test;
import org.mockito.ArgumentCaptor;

@SuppressWarnings("unchecked")
class VideoTaskServiceTests {

	private final VideoTaskRepository taskRepository = org.mockito.Mockito.mock(VideoTaskRepository.class);
	private final VideoTaskService service = new VideoTaskService(taskRepository);

	@Test
	void retryFailedTaskResetsStatusAndClearsError() {
		VideoTask failed = task("task-failed", VideoTask.TaskStatus.FAILED);
		failed.setErrorMessage("ffmpeg failed");
		when(taskRepository.findByTaskIdAndOwner("task-failed", "user-1")).thenReturn(Optional.of(failed));

		VideoTask result = service.retryFailedTask("task-failed", "user-1");

		assertThat(result).isSameAs(failed);
		assertThat(failed.getStatus()).isEqualTo(VideoTask.TaskStatus.QUEUED);
		assertThat(failed.getErrorMessage()).isNull();
	}

	@Test
	void retryFailedTaskRejectsNonFailedTask() {
		VideoTask queued = task("task-queued", VideoTask.TaskStatus.QUEUED);
		when(taskRepository.findByTaskIdAndOwner("task-queued", "user-1")).thenReturn(Optional.of(queued));

		assertThatThrownBy(() -> service.retryFailedTask("task-queued", "user-1"))
				.isInstanceOf(IllegalArgumentException.class)
				.hasMessageContaining("只有失败任务可以重试");

		assertThat(queued.getStatus()).isEqualTo(VideoTask.TaskStatus.QUEUED);
	}

	@Test
	void requeueStaleTasksResetsRetryableStatusesAndReturnsIds() {
		Instant cutoff = Instant.parse("2026-07-02T10:00:00Z");
		VideoTask queued = task("task-queued", VideoTask.TaskStatus.QUEUED);
		VideoTask transcribing = task("task-transcribing", VideoTask.TaskStatus.TRANSCRIBING);
		VideoTask summarizing = task("task-summarizing", VideoTask.TaskStatus.SUMMARIZING);
		when(taskRepository.findByStatusInAndUpdatedAtBefore(org.mockito.ArgumentMatchers.anyList(), eq(cutoff)))
				.thenReturn(List.of(queued, transcribing, summarizing));

		List<String> taskIds = service.requeueStaleTasks(cutoff);

		assertThat(taskIds).containsExactly("task-queued", "task-transcribing", "task-summarizing");
		assertThat(queued.getStatus()).isEqualTo(VideoTask.TaskStatus.QUEUED);
		assertThat(transcribing.getStatus()).isEqualTo(VideoTask.TaskStatus.QUEUED);
		assertThat(summarizing.getStatus()).isEqualTo(VideoTask.TaskStatus.QUEUED);

		ArgumentCaptor<List<VideoTask.TaskStatus>> statusesCaptor = ArgumentCaptor.forClass(List.class);
		verify(taskRepository).findByStatusInAndUpdatedAtBefore(statusesCaptor.capture(), eq(cutoff));
		assertThat(statusesCaptor.getValue()).containsExactly(
				VideoTask.TaskStatus.QUEUED,
				VideoTask.TaskStatus.TRANSCRIBING,
				VideoTask.TaskStatus.SUMMARIZING);
	}

	private static VideoTask task(String taskId, VideoTask.TaskStatus status) {
		VideoTask task = new VideoTask(taskId, "video-" + taskId, "user-1", "demo.mp4", "storage/demo.mp4");
		task.setStatus(status);
		return task;
	}
}
