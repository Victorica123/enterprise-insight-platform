package com.example.videoplatform.workflow;

import static org.mockito.ArgumentMatchers.anyString;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.verifyNoInteractions;
import static org.mockito.Mockito.when;
import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors.user;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.delete;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

import com.example.videoplatform.auth.JwtService;
import com.example.videoplatform.config.SecurityConfig;
import java.util.List;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.WebMvcTest;
import org.springframework.boot.test.mock.mockito.MockBean;
import org.springframework.context.annotation.Import;
import org.springframework.test.web.servlet.MockMvc;

@WebMvcTest(WorkflowController.class)
@Import(SecurityConfig.class)
class WorkflowControllerTests {

	@Autowired
	private MockMvc mockMvc;

	@MockBean
	private VideoTaskService videoTaskService;

	@MockBean
	private WorkflowPublisher workflowPublisher;

	@MockBean
	private WorkflowMetrics workflowMetrics;

	@MockBean
	private JwtService jwtService;

	@Test
	void rejectsAnonymousTaskListRequest() throws Exception {
		mockMvc.perform(get("/api/workflow/tasks"))
				.andExpect(status().isForbidden());

		verifyNoInteractions(videoTaskService);
	}

	@Test
	void listsOnlyAuthenticatedUsersTasks() throws Exception {
		VideoTask task = new VideoTask("task-1", "video-1", "alice", "demo.mp4", "storage/demo.mp4");
		when(videoTaskService.listTasksByOwner("alice")).thenReturn(List.of(task));

		mockMvc.perform(get("/api/workflow/tasks").with(user("alice")))
				.andExpect(status().isOk())
				.andExpect(jsonPath("$.success").value(true))
				.andExpect(jsonPath("$.data[0].taskId").value("task-1"))
				.andExpect(jsonPath("$.data[0].owner").value("alice"));

		verify(videoTaskService).listTasksByOwner("alice");
	}

	@Test
	void loadsTaskByIdAndAuthenticatedOwner() throws Exception {
		VideoTask task = new VideoTask("task-1", "video-1", "alice", "demo.mp4", "storage/demo.mp4");
		when(videoTaskService.requireTask("task-1", "alice")).thenReturn(task);

		mockMvc.perform(get("/api/workflow/tasks/task-1").with(user("alice")))
				.andExpect(status().isOk())
				.andExpect(jsonPath("$.data.taskId").value("task-1"));

		verify(videoTaskService).requireTask("task-1", "alice");
	}

	@Test
	void returnsBadRequestWhenOwnerScopedTaskIsMissing() throws Exception {
		when(videoTaskService.requireTask(anyString(), anyString()))
				.thenThrow(new IllegalArgumentException("task not found or forbidden"));

		mockMvc.perform(get("/api/workflow/tasks/task-2").with(user("alice")))
				.andExpect(status().isBadRequest())
				.andExpect(jsonPath("$.success").value(false));

		verify(videoTaskService).requireTask("task-2", "alice");
	}

	@Test
	void deletesTaskByIdAndAuthenticatedOwner() throws Exception {
		mockMvc.perform(delete("/api/workflow/tasks/task-1").with(user("alice")))
				.andExpect(status().isOk())
				.andExpect(jsonPath("$.success").value(true));

		verify(videoTaskService).deleteTask("task-1", "alice");
	}

	@Test
	void rejectsAnonymousDeleteRequest() throws Exception {
		mockMvc.perform(delete("/api/workflow/tasks/task-1"))
				.andExpect(status().isForbidden());

		verifyNoInteractions(videoTaskService);
	}

	@Test
	void retriesFailedTaskByAuthenticatedOwner() throws Exception {
		VideoTask task = new VideoTask("task-1", "video-1", "alice", "demo.mp4", "storage/demo.mp4");
		task.setStatus(VideoTask.TaskStatus.QUEUED);
		when(videoTaskService.retryFailedTask("task-1", "alice")).thenReturn(task);

		mockMvc.perform(post("/api/workflow/tasks/task-1/retry").with(user("alice")))
				.andExpect(status().isOk())
				.andExpect(jsonPath("$.success").value(true))
				.andExpect(jsonPath("$.data.taskId").value("task-1"))
				.andExpect(jsonPath("$.data.status").value("QUEUED"));

		verify(videoTaskService).retryFailedTask("task-1", "alice");
		verify(workflowMetrics).incrementRequeue("manual");
		verify(workflowPublisher).publish("task-1");
	}

	@Test
	void rejectsAnonymousRetryRequest() throws Exception {
		mockMvc.perform(post("/api/workflow/tasks/task-1/retry"))
				.andExpect(status().isForbidden());

		verifyNoInteractions(videoTaskService);
		verifyNoInteractions(workflowPublisher);
	}
}
