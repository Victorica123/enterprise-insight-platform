package com.example.videoplatform.workflow;

import java.util.Map;
import java.util.UUID;
import java.util.concurrent.ConcurrentHashMap;
import org.springframework.stereotype.Service;

@Service
public class VideoTaskService {

	private final Map<String, VideoTask> tasks = new ConcurrentHashMap<>();

	public VideoTask createTask(String owner, String fileName, String storagePath) {
		String taskId = UUID.randomUUID().toString();
		String videoId = UUID.randomUUID().toString();
		VideoTask task = new VideoTask(taskId, videoId, owner, fileName, storagePath);
		tasks.put(taskId, task);
		return task;
	}

	public VideoTask requireTask(String taskId) {
		VideoTask task = tasks.get(taskId);
		if (task == null) {
			throw new IllegalArgumentException("任务不存在: " + taskId);
		}
		return task;
	}
}
