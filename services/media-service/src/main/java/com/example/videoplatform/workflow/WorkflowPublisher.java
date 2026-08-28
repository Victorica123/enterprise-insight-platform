package com.example.videoplatform.workflow;

public interface WorkflowPublisher {

	/**
	 * 发布视频处理任务
	 *
	 * @param taskId 任务 ID
	 */
	void publish(String taskId);
}
