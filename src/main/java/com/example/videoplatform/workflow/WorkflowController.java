package com.example.videoplatform.workflow;

import com.example.videoplatform.common.ApiResponse;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/api/workflow")
public class WorkflowController {

	private final VideoTaskService videoTaskService;

	public WorkflowController(VideoTaskService videoTaskService) {
		this.videoTaskService = videoTaskService;
	}

	@GetMapping("/tasks/{taskId}")
	public ApiResponse<WorkflowDtos.TaskView> getTask(@PathVariable String taskId) {
		return ApiResponse.ok(WorkflowDtos.TaskView.from(videoTaskService.requireTask(taskId)));
	}
}
