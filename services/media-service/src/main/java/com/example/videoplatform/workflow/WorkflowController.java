package com.example.videoplatform.workflow;

import com.example.videoplatform.common.ApiResponse;
import com.example.videoplatform.config.AppProperties;
import com.example.videoplatform.auth.WorkspacePrincipal;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.http.HttpStatus;
import org.springframework.security.core.Authentication;
import org.springframework.web.bind.annotation.DeleteMapping;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.server.ResponseStatusException;

import java.util.List;

@RestController
@RequestMapping("/api/workflow")
public class WorkflowController {

	private final VideoTaskService videoTaskService;
	private final MediaLifecycleService mediaLifecycleService;
	private final WorkflowPublisher workflowPublisher;
	private final WorkflowMetrics workflowMetrics;
	private final AppProperties appProperties;
	private final boolean mqEnabled;

	public WorkflowController(VideoTaskService videoTaskService, MediaLifecycleService mediaLifecycleService,
			WorkflowPublisher workflowPublisher,
			WorkflowMetrics workflowMetrics, AppProperties appProperties,
			@Value("${app.mq.enabled:false}") boolean mqEnabled) {
		this.videoTaskService = videoTaskService;
		this.mediaLifecycleService = mediaLifecycleService;
		this.workflowPublisher = workflowPublisher;
		this.workflowMetrics = workflowMetrics;
		this.appProperties = appProperties;
		this.mqEnabled = mqEnabled;
	}

	/**
	 * 查询单个任务（带owner校验，只能查自己的）
	 */
	@GetMapping("/tasks/{taskId}")
	public ApiResponse<WorkflowDtos.TaskView> getTask(Authentication authentication, @PathVariable String taskId) {
		WorkspacePrincipal principal = WorkspacePrincipal.require(authentication);
		return ApiResponse.ok(WorkflowDtos.TaskView.from(videoTaskService.requireTaskForWorkspace(
				taskId, principal.tenantId(), principal.userId(), principal.isTeam())));
	}

	/**
	 * 查询当前用户的所有任务（我的视频列表）
	 */
	@GetMapping("/tasks")
	public ApiResponse<List<WorkflowDtos.TaskView>> listMyTasks(Authentication authentication) {
		WorkspacePrincipal principal = WorkspacePrincipal.require(authentication);
		List<VideoTask> tasks = videoTaskService.listTasksForWorkspace(
				principal.tenantId(), principal.userId(), principal.isTeam());
		return ApiResponse.ok(tasks.stream().map(WorkflowDtos.TaskView::from).toList());
	}

	@GetMapping("/quota")
	public ApiResponse<WorkflowDtos.TaskQuotaView> getTaskQuota(Authentication authentication) {
		return ApiResponse.ok(videoTaskService.getTaskQuota(WorkspacePrincipal.require(authentication).userId()));
	}

	@GetMapping("/runtime")
	public ApiResponse<WorkflowDtos.RuntimeView> getRuntime(Authentication authentication) {
		WorkspacePrincipal.require(authentication);
		return ApiResponse.ok(new WorkflowDtos.RuntimeView(
				mqEnabled ? "rocketmq" : "local-async",
				mqEnabled,
				appProperties.getTranscript().getMockDelayMs(),
				appProperties.getQuota().getMaxActiveTasksPerUser(),
				appProperties.getMq().getConsumerThreads(),
				appProperties.getStorage().getType()));
	}

	@DeleteMapping("/tasks/{taskId}")
	public ApiResponse<WorkflowDtos.TaskDeletionView> deleteTask(Authentication authentication,
			@PathVariable String taskId) {
		WorkspacePrincipal principal = requireWriter(authentication);
		VideoTask task = videoTaskService.requireTaskForWorkspace(
				taskId, principal.tenantId(), principal.userId(), principal.isTeam());
		MediaLifecycleService.DeletionPlan plan = mediaLifecycleService.scheduleTaskDeletion(taskId, task.getOwner());
		return ApiResponse.ok(mediaLifecycleService.attemptCleanup(plan));
	}

	@PostMapping("/tasks/{taskId}/retry")
	public ApiResponse<WorkflowDtos.TaskView> retryTask(Authentication authentication, @PathVariable String taskId) {
		WorkspacePrincipal principal = requireWriter(authentication);
		VideoTask task = videoTaskService.retryFailedTaskForWorkspace(
				taskId, principal.tenantId(), principal.userId(), principal.isTeam());
		workflowMetrics.incrementRequeue("manual");
		workflowPublisher.publish(taskId);
		return ApiResponse.ok(WorkflowDtos.TaskView.from(task));
	}

	private static WorkspacePrincipal requireWriter(Authentication authentication) {
		WorkspacePrincipal principal = WorkspacePrincipal.require(authentication);
		if (!principal.canWrite()) {
			throw new ResponseStatusException(HttpStatus.FORBIDDEN, "当前角色没有写权限");
		}
		return principal;
	}
}
