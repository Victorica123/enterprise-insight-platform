package com.example.videoplatform.workflow;

import com.example.videoplatform.common.ApiResponse;
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
	private final WorkflowPublisher workflowPublisher;
	private final WorkflowMetrics workflowMetrics;

	public WorkflowController(VideoTaskService videoTaskService, WorkflowPublisher workflowPublisher,
			WorkflowMetrics workflowMetrics) {
		this.videoTaskService = videoTaskService;
		this.workflowPublisher = workflowPublisher;
		this.workflowMetrics = workflowMetrics;
	}

	/**
	 * 查询单个任务（带owner校验，只能查自己的）
	 */
	@GetMapping("/tasks/{taskId}")
	public ApiResponse<WorkflowDtos.TaskView> getTask(Authentication authentication, @PathVariable String taskId) {
		String currentUser = currentUsername(authentication);
		return ApiResponse.ok(WorkflowDtos.TaskView.from(videoTaskService.requireTask(taskId, currentUser)));
	}

	/**
	 * 查询当前用户的所有任务（我的视频列表）
	 */
	@GetMapping("/tasks")
	public ApiResponse<List<WorkflowDtos.TaskView>> listMyTasks(Authentication authentication) {
		String currentUser = currentUsername(authentication);
		List<VideoTask> tasks = videoTaskService.listTasksByOwner(currentUser);
		return ApiResponse.ok(tasks.stream().map(WorkflowDtos.TaskView::from).toList());
	}

	@DeleteMapping("/tasks/{taskId}")
	public ApiResponse<Void> deleteTask(Authentication authentication, @PathVariable String taskId) {
		String currentUser = currentUsername(authentication);
		videoTaskService.deleteTask(taskId, currentUser);
		return ApiResponse.ok(null);
	}

	@PostMapping("/tasks/{taskId}/retry")
	public ApiResponse<WorkflowDtos.TaskView> retryTask(Authentication authentication, @PathVariable String taskId) {
		String currentUser = currentUsername(authentication);
		VideoTask task = videoTaskService.retryFailedTask(taskId, currentUser);
		workflowMetrics.incrementRequeue("manual");
		workflowPublisher.publish(taskId);
		return ApiResponse.ok(WorkflowDtos.TaskView.from(task));
	}

	private String currentUsername(Authentication authentication) {
		if (authentication == null || !authentication.isAuthenticated()
				|| "anonymousUser".equals(authentication.getPrincipal())) {
			throw new ResponseStatusException(HttpStatus.UNAUTHORIZED, "用户未登录");
		}
		return authentication.getName();
	}
}
