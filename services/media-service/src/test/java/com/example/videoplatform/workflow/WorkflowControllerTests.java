package com.example.videoplatform.workflow;

import static org.mockito.ArgumentMatchers.anyString;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.verifyNoInteractions;
import static org.mockito.Mockito.when;
import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors.authentication;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.delete;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

import com.example.videoplatform.auth.JwtService;
import com.example.videoplatform.auth.WorkspacePrincipal;
import com.example.videoplatform.config.SecurityConfig;
import java.util.List;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.WebMvcTest;
import org.springframework.boot.test.mock.mockito.MockBean;
import org.springframework.context.annotation.Import;
import org.springframework.security.authentication.UsernamePasswordAuthenticationToken;
import org.springframework.security.core.authority.SimpleGrantedAuthority;
import org.springframework.test.web.servlet.MockMvc;
import org.springframework.test.web.servlet.request.RequestPostProcessor;

@WebMvcTest(WorkflowController.class)
@Import(SecurityConfig.class)
class WorkflowControllerTests {

	@Autowired MockMvc mockMvc;
	@MockBean VideoTaskService videoTaskService;
	@MockBean MediaLifecycleService mediaLifecycleService;
	@MockBean WorkflowMetrics workflowMetrics;
	@MockBean ModelEgressPolicy modelEgressPolicy;
	@MockBean JwtService jwtService;
	@MockBean com.example.videoplatform.auth.TokenBlacklist tokenBlacklist;

	@Test
	void rejectsAnonymousTaskListRequest() throws Exception {
		mockMvc.perform(get("/api/workflow/tasks")).andExpect(status().isForbidden());
		verifyNoInteractions(videoTaskService);
	}

	@Test
	void listsTeamTasksForAuthenticatedMember() throws Exception {
		VideoTask task = taskOwnedBy("owner");
		when(videoTaskService.listTasksForWorkspace("tenant-a", "alice", true)).thenReturn(List.of(task));
		mockMvc.perform(get("/api/workflow/tasks").with(workspaceUser("alice", "member")))
				.andExpect(status().isOk())
				.andExpect(jsonPath("$.data[0].taskId").value("task-1"))
				.andExpect(jsonPath("$.data[0].owner").value("owner"));
		verify(videoTaskService).listTasksForWorkspace("tenant-a", "alice", true);
	}

	@Test
	void returnsOwnerTaskQuota() throws Exception {
		when(videoTaskService.getTaskQuota("alice")).thenReturn(new WorkflowDtos.TaskQuotaView(3, 5, 2, true));
		mockMvc.perform(get("/api/workflow/quota").with(workspaceUser("alice", "admin")))
				.andExpect(status().isOk()).andExpect(jsonPath("$.data.activeTasks").value(3));
		verify(videoTaskService).getTaskQuota("alice");
	}

	@Test
	void exposesCurrentAsyncRuntimeForVisualLab() throws Exception {
		mockMvc.perform(get("/api/workflow/runtime").with(workspaceUser("alice", "admin")))
				.andExpect(status().isOk())
				.andExpect(jsonPath("$.data.dispatchMode").value("local-async"))
				.andExpect(jsonPath("$.data.transcriptMode").value("mock"))
				.andExpect(jsonPath("$.data.summaryMode").value("mock"));
	}

	@Test
	void loadsTaskByTeamScope() throws Exception {
		when(videoTaskService.requireTaskForWorkspace("task-1", "tenant-a", "alice", true))
				.thenReturn(taskOwnedBy("owner"));
		mockMvc.perform(get("/api/workflow/tasks/task-1").with(workspaceUser("alice", "member")))
				.andExpect(status().isOk()).andExpect(jsonPath("$.data.taskId").value("task-1"));
		verify(videoTaskService).requireTaskForWorkspace("task-1", "tenant-a", "alice", true);
	}

	@Test
	void returnsBadRequestWhenScopedTaskIsMissing() throws Exception {
		when(videoTaskService.requireTaskForWorkspace(anyString(), anyString(), anyString(),
				org.mockito.ArgumentMatchers.anyBoolean()))
				.thenThrow(new IllegalArgumentException("task not found or forbidden"));
		mockMvc.perform(get("/api/workflow/tasks/task-2").with(workspaceUser("alice", "member")))
				.andExpect(status().isBadRequest());
		verify(videoTaskService).requireTaskForWorkspace("task-2", "tenant-a", "alice", true);
	}

	@Test
	void deletesTeamTaskUsingCreatorForLifecycleAudit() throws Exception {
		MediaLifecycleService.DeletionPlan plan = new MediaLifecycleService.DeletionPlan("task-1", "cleanup-1", "PENDING");
		when(videoTaskService.requireTaskForWorkspace("task-1", "tenant-a", "alice", true))
				.thenReturn(taskOwnedBy("owner"));
		when(mediaLifecycleService.scheduleTaskDeletion("task-1", "owner")).thenReturn(plan);
		when(mediaLifecycleService.attemptCleanup(plan))
				.thenReturn(new WorkflowDtos.TaskDeletionView("task-1", "DELETED"));

		mockMvc.perform(delete("/api/workflow/tasks/task-1").with(workspaceUser("alice", "admin")))
				.andExpect(status().isOk())
				.andExpect(jsonPath("$.data.mediaCleanupStatus").value("DELETED"));
		verify(mediaLifecycleService).scheduleTaskDeletion("task-1", "owner");
	}

	@Test
	void rejectsAnonymousDeleteRequest() throws Exception {
		mockMvc.perform(delete("/api/workflow/tasks/task-1")).andExpect(status().isForbidden());
		verifyNoInteractions(videoTaskService, mediaLifecycleService);
	}

	@Test
	void retriesFailedTaskByTeamScope() throws Exception {
		VideoTask task = taskOwnedBy("owner");
		task.setStatus(VideoTask.TaskStatus.QUEUED);
		when(videoTaskService.retryFailedTaskForWorkspace("task-1", "tenant-a", "alice", true)).thenReturn(task);
		mockMvc.perform(post("/api/workflow/tasks/task-1/retry").with(workspaceUser("alice", "member")))
				.andExpect(status().isOk()).andExpect(jsonPath("$.data.status").value("QUEUED"));
		verify(videoTaskService).retryFailedTaskForWorkspace("task-1", "tenant-a", "alice", true);
		verify(workflowMetrics).incrementRequeue("manual");
	}

	@Test
	void rejectsAnonymousRetryRequest() throws Exception {
		mockMvc.perform(post("/api/workflow/tasks/task-1/retry")).andExpect(status().isForbidden());
		verifyNoInteractions(videoTaskService);
	}

	@Test
	void letsViewerReadButNotRetryTeamTasks() throws Exception {
		when(videoTaskService.requireTaskForWorkspace("task-1", "tenant-a", "viewer", true))
				.thenReturn(taskOwnedBy("owner"));
		mockMvc.perform(get("/api/workflow/tasks/task-1").with(workspaceUser("viewer", "viewer")))
				.andExpect(status().isOk());
		mockMvc.perform(post("/api/workflow/tasks/task-1/retry").with(workspaceUser("viewer", "viewer")))
				.andExpect(status().isForbidden());
	}

	private static VideoTask taskOwnedBy(String owner) {
		return new VideoTask("task-1", "video-1", owner, "demo.mp4", "storage/demo.mp4");
	}

	private static RequestPostProcessor workspaceUser(String userId, String role) {
		String jwtRole = "member".equals(role) ? "operator" : role;
		WorkspacePrincipal principal = new WorkspacePrincipal(userId, userId, "tenant-a", jwtRole, "team");
		return authentication(new UsernamePasswordAuthenticationToken(
				principal, null, List.of(new SimpleGrantedAuthority("ROLE_" + jwtRole.toUpperCase()))));
	}
}
