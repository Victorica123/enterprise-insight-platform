package com.example.videoplatform.workflow;

import java.time.Instant;
import java.util.List;
import java.util.Optional;
import org.springframework.data.jpa.repository.JpaRepository;
import org.springframework.data.jpa.repository.Modifying;
import org.springframework.data.jpa.repository.Query;
import org.springframework.data.repository.query.Param;
import org.springframework.stereotype.Repository;

@Repository
public interface VideoTaskRepository extends JpaRepository<VideoTask, String> {

	/**
	 * 原子状态推进：仅当任务仍处于 expected 状态时更新为 next，返回受影响行数。
	 * 用于 MQ 至少一次投递下的幂等占位（QUEUED→TRANSCRIBING），并发消费者中只有一个能影响 1 行。
	 */
	@Modifying
	@Query("update VideoTask t set t.status = :next, t.updatedAt = :now "
			+ "where t.taskId = :taskId and t.status = :expected")
	int updateStatusIfCurrent(@Param("taskId") String taskId,
			@Param("expected") VideoTask.TaskStatus expected,
			@Param("next") VideoTask.TaskStatus next,
			@Param("now") Instant now);

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
