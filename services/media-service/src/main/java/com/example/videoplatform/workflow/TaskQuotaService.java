package com.example.videoplatform.workflow;

import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;
import java.time.Instant;
import java.util.List;
import com.example.videoplatform.auth.UserAccount;
import com.example.videoplatform.auth.UserAccountRepository;
import com.example.videoplatform.config.QuotaProperties;

@Service
public class TaskQuotaService {
	private final VideoTaskRepository taskRepository;
	private final UserAccountRepository userAccountRepository;
	private final QuotaProperties properties;

	public TaskQuotaService(VideoTaskRepository taskRepository, UserAccountRepository userAccountRepository, QuotaProperties properties) {
		this.taskRepository = taskRepository;
		this.userAccountRepository = userAccountRepository;
		this.properties = properties;
	}

	@Transactional
	public void assertCanCreateTask(String owner) {
		lockOwner(owner);
		assertWithinQuota(owner);
	}

	public void assertWithinQuota(String owner) {
		int limit = properties.getMaxActiveTasksPerUser();
		if (limit <= 0) {
			return;
		}
		long activeCount = countActiveTasks(owner);
		if (activeCount >= limit) {
			throw new ActiveTaskLimitExceededException(limit, activeCount);
		}
	}

	@Transactional(readOnly = true)
	public WorkflowDtos.TaskQuotaView getTaskQuota(String owner) {
		int limit = properties.getMaxActiveTasksPerUser();
		long activeCount = countActiveTasks(owner);
		long remaining = limit > 0 ? Math.max(0, limit - activeCount) : -1;
		return new WorkflowDtos.TaskQuotaView(activeCount, limit, remaining, limit > 0);
	}

	private long countActiveTasks(String owner) {
		return taskRepository.countByOwnerAndStatusIn(owner, List.of(
				VideoTask.TaskStatus.QUEUED,
				VideoTask.TaskStatus.TRANSCRIBING,
				VideoTask.TaskStatus.SUMMARIZING));
	}

	public UserAccount lockOwner(String owner) {
		return userAccountRepository.findByUserId(owner)
				.orElseThrow(() -> new IllegalArgumentException("用户不存在: " + owner));
	}
}
