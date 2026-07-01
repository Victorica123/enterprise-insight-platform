package com.example.videoplatform.workflow;

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
}
