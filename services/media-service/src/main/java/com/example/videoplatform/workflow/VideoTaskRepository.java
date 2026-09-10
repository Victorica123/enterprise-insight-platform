package com.example.videoplatform.workflow;

import java.time.Instant;
import java.util.List;
import java.util.Optional;
import org.springframework.data.jpa.repository.JpaRepository;
import org.springframework.data.jpa.repository.Modifying;
import org.springframework.data.jpa.repository.Query;
import org.springframework.data.jpa.repository.Lock;
import jakarta.persistence.LockModeType;
import org.springframework.data.domain.Pageable;
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

	/** Atomically claims a queued task with a renewable fencing lease. */
	@Modifying
	@Query("update VideoTask t set t.status = :next, t.updatedAt = :now, "
			+ "t.processingLeaseId = :leaseId, t.processingLeaseExpiresAt = :leaseExpiresAt "
			+ "where t.taskId = :taskId and t.status = :expected")
	int claimWithLease(@Param("taskId") String taskId,
			@Param("expected") VideoTask.TaskStatus expected,
			@Param("next") VideoTask.TaskStatus next,
			@Param("leaseId") String leaseId,
			@Param("leaseExpiresAt") Instant leaseExpiresAt,
			@Param("now") Instant now);

	@Modifying(clearAutomatically = true, flushAutomatically = true)
	@Query("update VideoTask t set t.processingLeaseExpiresAt = :leaseExpiresAt, t.updatedAt = :now "
			+ "where t.taskId = :taskId and t.status in :statuses and t.processingLeaseId = :leaseId")
	int renewLease(@Param("taskId") String taskId, @Param("leaseId") String leaseId,
			@Param("statuses") List<VideoTask.TaskStatus> statuses,
			@Param("leaseExpiresAt") Instant leaseExpiresAt, @Param("now") Instant now);

	@Modifying(clearAutomatically = true, flushAutomatically = true)
	@Query("update VideoTask t set t.transcript = :transcript, "
			+ "t.transcriptSegmentsJson = :segmentsJson, t.transcriptLanguage = :language, "
			+ "t.transcriptDurationMs = :durationMs, t.status = :next, t.updatedAt = :now "
			+ "where t.taskId = :taskId and t.status = :expected and t.processingLeaseId = :leaseId")
	int completeTranscriptWithLease(@Param("taskId") String taskId,
			@Param("expected") VideoTask.TaskStatus expected,
			@Param("next") VideoTask.TaskStatus next,
			@Param("leaseId") String leaseId, @Param("transcript") String transcript,
			@Param("segmentsJson") String segmentsJson, @Param("language") String language,
			@Param("durationMs") Long durationMs, @Param("now") Instant now);

	@Modifying(clearAutomatically = true, flushAutomatically = true)
	@Query("update VideoTask t set t.summary = :summary, t.status = :next, "
			+ "t.processingLeaseId = null, t.processingLeaseExpiresAt = null, t.updatedAt = :now "
			+ "where t.taskId = :taskId and t.status = :expected and t.processingLeaseId = :leaseId")
	int completeSummaryWithLease(@Param("taskId") String taskId,
			@Param("expected") VideoTask.TaskStatus expected,
			@Param("next") VideoTask.TaskStatus next,
			@Param("leaseId") String leaseId, @Param("summary") String summary,
			@Param("now") Instant now);

	@Modifying(clearAutomatically = true, flushAutomatically = true)
	@Query("update VideoTask t set t.status = :failed, t.errorMessage = :errorMessage, "
			+ "t.processingLeaseId = null, t.processingLeaseExpiresAt = null, t.updatedAt = :now "
			+ "where t.taskId = :taskId and t.status in :statuses and t.processingLeaseId = :leaseId")
	int markFailedWithLease(@Param("taskId") String taskId,
			@Param("statuses") List<VideoTask.TaskStatus> statuses,
			@Param("failed") VideoTask.TaskStatus failed, @Param("leaseId") String leaseId,
			@Param("errorMessage") String errorMessage, @Param("now") Instant now);

	@Modifying(clearAutomatically = true, flushAutomatically = true)
	@Query("update VideoTask t set t.transcript = :transcript, "
			+ "t.transcriptSegmentsJson = :segmentsJson, t.transcriptLanguage = :language, "
			+ "t.transcriptDurationMs = :durationMs, t.summary = :summary, "
			+ "t.status = :completed, t.processingLeaseId = null, "
			+ "t.processingLeaseExpiresAt = null, t.updatedAt = :now "
			+ "where t.taskId = :taskId and t.status in :statuses and t.processingLeaseId = :leaseId")
	int completeContentWithLease(@Param("taskId") String taskId,
			@Param("statuses") List<VideoTask.TaskStatus> statuses,
			@Param("completed") VideoTask.TaskStatus completed, @Param("leaseId") String leaseId,
			@Param("transcript") String transcript, @Param("segmentsJson") String segmentsJson,
			@Param("language") String language, @Param("durationMs") Long durationMs,
			@Param("summary") String summary, @Param("now") Instant now);

	/**
	 * 查询某个用户的所有任务（用于"我的视频"列表）
	 */
	List<VideoTask> findByOwnerOrderByCreatedAtDesc(String owner);

	List<VideoTask> findByTenantIdOrderByCreatedAtDesc(String tenantId);

	List<VideoTask> findByTenantIdAndOwnerOrderByCreatedAtDesc(String tenantId, String owner);

	/**
	 * 按owner + taskId查询（带权限校验）
	 */
	Optional<VideoTask> findByTaskIdAndOwner(String taskId, String owner);

	Optional<VideoTask> findByTaskIdAndTenantId(String taskId, String tenantId);

	Optional<VideoTask> findByTaskIdAndTenantIdAndOwner(String taskId, String tenantId, String owner);

	Optional<VideoTask> findFirstByOwnerAndStoragePathOrderByCreatedAtDesc(String owner, String storagePath);

	boolean existsByStoragePath(String storagePath);

	@Lock(LockModeType.PESSIMISTIC_WRITE)
	@Query("select t from VideoTask t where t.status in :statuses and t.createdAt < :cutoff "
			+ "and t.storagePath is not null order by t.createdAt asc")
	List<VideoTask> findMediaRetentionCandidates(
			@Param("statuses") List<VideoTask.TaskStatus> statuses,
			@Param("cutoff") Instant cutoff, Pageable pageable);

	@Lock(LockModeType.PESSIMISTIC_WRITE)
	@Query("select t from VideoTask t where t.status in :statuses and t.createdAt < :cutoff "
			+ "and t.transcript is not null order by t.createdAt asc")
	List<VideoTask> findTranscriptRetentionCandidates(
			@Param("statuses") List<VideoTask.TaskStatus> statuses,
			@Param("cutoff") Instant cutoff, Pageable pageable);

	long countByOwnerAndStatusIn(String owner, List<VideoTask.TaskStatus> statuses);

	/**
	 * 按内容指纹查询所有任务（用于处理完成后向同内容的所有任务 fan-out 结果）
	 */
	List<VideoTask> findByContentMd5(String contentMd5);

	List<VideoTask> findByTenantIdAndContentMd5(String tenantId, String contentMd5);

	/**
	 * 查找候选过期任务。候选查询与后续条件更新分开，避免把实体快照交给重入队逻辑。
	 */
	@Query("select t.taskId from VideoTask t where t.status in :statuses and "
			+ "((t.processingLeaseExpiresAt is not null and t.processingLeaseExpiresAt <= :now) "
			+ "or (t.processingLeaseExpiresAt is null and t.updatedAt < :cutoff))")
	List<String> findStaleTaskIds(@Param("statuses") List<VideoTask.TaskStatus> statuses,
			@Param("now") Instant now, @Param("cutoff") Instant cutoff);

	/**
	 * Atomically requeues only the stale version observed by the reaper. A live
	 * worker that renewed or completed the task therefore cannot be overwritten.
	 */
	@Modifying(clearAutomatically = true, flushAutomatically = true)
	@Query("update VideoTask t set t.status = :queued, t.processingLeaseId = null, "
			+ "t.processingLeaseExpiresAt = null, t.updatedAt = :now "
			+ "where t.taskId = :taskId and t.status in :statuses and "
			+ "((t.processingLeaseExpiresAt is not null and t.processingLeaseExpiresAt <= :now) "
			+ "or (t.processingLeaseExpiresAt is null and t.updatedAt < :cutoff))")
	int requeueIfStale(@Param("taskId") String taskId,
			@Param("statuses") List<VideoTask.TaskStatus> statuses,
			@Param("queued") VideoTask.TaskStatus queued, @Param("now") Instant now,
			@Param("cutoff") Instant cutoff);
}
