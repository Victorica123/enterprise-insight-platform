package com.example.videoplatform.workflow;

import java.time.Instant;
import org.springframework.data.jpa.repository.JpaRepository;
import org.springframework.stereotype.Repository;

import java.util.List;
import java.util.Optional;

@Repository
public interface VideoTaskRepository extends JpaRepository<VideoTask, String> {

	/**
	 * 查询某个用户的所有任务（用于"我的视频"列表）
	 */
	List<VideoTask> findByOwnerOrderByCreatedAtDesc(String owner);

	/**
	 * 按owner + taskId查询（带权限校验）
	 */
	Optional<VideoTask> findByTaskIdAndOwner(String taskId, String owner);

	Optional<VideoTask> findFirstByOwnerAndStoragePathOrderByCreatedAtDesc(String owner, String storagePath);

	boolean existsByStoragePath(String storagePath);

	long countByOwnerAndStatusIn(String owner, List<VideoTask.TaskStatus> statuses);

	/**
	 * 按内容指纹查询所有任务（用于处理完成后向同内容的所有任务 fan-out 结果）
	 */
	List<VideoTask> findByContentMd5(String contentMd5);

	/**
	 * 查找长时间停留在非终态/待处理状态的任务，用于定时补偿重投递。
	 */
	List<VideoTask> findByStatusInAndUpdatedAtBefore(List<VideoTask.TaskStatus> statuses, Instant cutoff);
}
