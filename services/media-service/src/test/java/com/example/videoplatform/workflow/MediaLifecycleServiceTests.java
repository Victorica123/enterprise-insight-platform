package com.example.videoplatform.workflow;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;
import static org.mockito.ArgumentMatchers.any;
import static org.mockito.Mockito.never;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.when;

import com.example.videoplatform.media.MediaStorageService;
import io.micrometer.core.instrument.simple.SimpleMeterRegistry;
import java.io.IOException;
import java.util.Optional;
import org.junit.jupiter.api.Test;

class MediaLifecycleServiceTests {

	private final VideoTaskRepository taskRepository = org.mockito.Mockito.mock(VideoTaskRepository.class);
	private final MediaCleanupJobRepository cleanupJobRepository =
			org.mockito.Mockito.mock(MediaCleanupJobRepository.class);
	private final MediaStorageService mediaStorageService = org.mockito.Mockito.mock(MediaStorageService.class);
	private final SimpleMeterRegistry meterRegistry = new SimpleMeterRegistry();
	private final MediaLifecycleService service = new MediaLifecycleService(
			taskRepository, cleanupJobRepository, mediaStorageService, meterRegistry);

	@Test
	void deletesTerminalTaskAndItsLastMediaReference() throws Exception {
		VideoTask task = task("task-1", VideoTask.TaskStatus.COMPLETED);
		when(taskRepository.findByTaskIdAndOwner("task-1", "alice")).thenReturn(Optional.of(task));
		when(taskRepository.existsByStoragePath("storage/demo.mp4")).thenReturn(false);
		when(cleanupJobRepository.save(any(MediaCleanupJob.class))).thenAnswer(invocation -> invocation.getArgument(0));

		MediaLifecycleService.DeletionPlan plan = service.scheduleTaskDeletion("task-1", "alice");
		MediaCleanupJob job = captureSavedJob();
		when(cleanupJobRepository.findById(job.getJobId())).thenReturn(Optional.of(job));

		WorkflowDtos.TaskDeletionView result = service.attemptCleanup(plan);

		assertThat(result.mediaCleanupStatus()).isEqualTo("DELETED");
		verify(taskRepository).delete(task);
		verify(taskRepository).flush();
		verify(mediaStorageService).delete("storage/demo.mp4");
		verify(cleanupJobRepository).deleteById(job.getJobId());
	}

	@Test
	void keepsMediaReferencedByAnotherTask() throws Exception {
		VideoTask task = task("task-1", VideoTask.TaskStatus.FAILED);
		when(taskRepository.findByTaskIdAndOwner("task-1", "alice")).thenReturn(Optional.of(task));
		when(taskRepository.existsByStoragePath("storage/demo.mp4")).thenReturn(true);
		when(cleanupJobRepository.save(any(MediaCleanupJob.class))).thenAnswer(invocation -> invocation.getArgument(0));

		MediaLifecycleService.DeletionPlan plan = service.scheduleTaskDeletion("task-1", "alice");
		MediaCleanupJob job = captureSavedJob();
		when(cleanupJobRepository.findById(job.getJobId())).thenReturn(Optional.of(job));
		WorkflowDtos.TaskDeletionView result = service.attemptCleanup(plan);

		assertThat(result.mediaCleanupStatus()).isEqualTo("RETAINED_SHARED");
		verify(mediaStorageService, never()).delete(any());
		verify(cleanupJobRepository).deleteById(job.getJobId());
	}

	@Test
	void rejectsDeletionWhileTaskIsActive() {
		VideoTask task = task("task-1", VideoTask.TaskStatus.TRANSCRIBING);
		when(taskRepository.findByTaskIdAndOwner("task-1", "alice")).thenReturn(Optional.of(task));

		assertThatThrownBy(() -> service.scheduleTaskDeletion("task-1", "alice"))
				.isInstanceOf(IllegalArgumentException.class)
				.hasMessageContaining("任务处理中");

		verify(taskRepository, never()).delete(any());
		verifyNoStorageDelete();
	}

	@Test
	void keepsDurableRetryJobWhenStorageDeleteFails() throws Exception {
		VideoTask task = task("task-1", VideoTask.TaskStatus.COMPLETED);
		when(taskRepository.findByTaskIdAndOwner("task-1", "alice")).thenReturn(Optional.of(task));
		when(taskRepository.existsByStoragePath("storage/demo.mp4")).thenReturn(false);
		when(cleanupJobRepository.save(any(MediaCleanupJob.class))).thenAnswer(invocation -> invocation.getArgument(0));

		MediaLifecycleService.DeletionPlan plan = service.scheduleTaskDeletion("task-1", "alice");
		MediaCleanupJob job = captureSavedJob();
		when(cleanupJobRepository.findById(job.getJobId())).thenReturn(Optional.of(job));
		org.mockito.Mockito.doThrow(new IOException("MinIO unavailable"))
				.when(mediaStorageService).delete("storage/demo.mp4");

		WorkflowDtos.TaskDeletionView result = service.attemptCleanup(plan);

		assertThat(result.mediaCleanupStatus()).isEqualTo("RETRY_PENDING");
		assertThat(job.getAttemptCount()).isEqualTo(1);
		assertThat(job.getLastError()).contains("MinIO unavailable");
		verify(cleanupJobRepository, org.mockito.Mockito.times(2)).save(job);
		verify(cleanupJobRepository, never()).deleteById(job.getJobId());
	}

	private MediaCleanupJob captureSavedJob() {
		org.mockito.ArgumentCaptor<MediaCleanupJob> captor =
				org.mockito.ArgumentCaptor.forClass(MediaCleanupJob.class);
		verify(cleanupJobRepository).save(captor.capture());
		return captor.getValue();
	}

	private void verifyNoStorageDelete() {
		try {
			verify(mediaStorageService, never()).delete(any());
		} catch (IOException exception) {
			throw new AssertionError(exception);
		}
	}

	private static VideoTask task(String taskId, VideoTask.TaskStatus status) {
		VideoTask task = new VideoTask(taskId, "video-1", "alice", "demo.mp4", "storage/demo.mp4");
		task.setStatus(status);
		return task;
	}
}
