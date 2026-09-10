package com.example.videoplatform.workflow;

import java.time.Instant;
import java.util.List;
import org.springframework.data.jpa.repository.JpaRepository;
import org.springframework.data.jpa.repository.Modifying;
import org.springframework.data.jpa.repository.Query;
import org.springframework.data.repository.query.Param;

public interface WorkflowDispatchOutboxRepository extends JpaRepository<WorkflowDispatchOutbox, String> {

	List<WorkflowDispatchOutbox> findTop50ByStatusAndNextAttemptAtLessThanEqualOrderByCreatedAt(
			WorkflowDispatchOutbox.DispatchStatus status, Instant now);

	List<WorkflowDispatchOutbox> findTop50ByStatusAndClaimExpiresAtLessThanEqualOrderByCreatedAt(
			WorkflowDispatchOutbox.DispatchStatus status, Instant now);

	@Modifying(clearAutomatically = true, flushAutomatically = true)
	@Query("""
			update WorkflowDispatchOutbox e
			set e.status = :claimed, e.claimId = :claimId, e.claimExpiresAt = :claimExpiresAt
			where e.taskId = :taskId
			  and ((e.status = :pending and e.nextAttemptAt <= :now)
			       or (e.status = :claimed and e.claimExpiresAt <= :now))
			""")
	int claimIfAvailable(@Param("taskId") String taskId,
			@Param("pending") WorkflowDispatchOutbox.DispatchStatus pending,
			@Param("claimed") WorkflowDispatchOutbox.DispatchStatus claimed,
			@Param("now") Instant now, @Param("claimId") String claimId,
			@Param("claimExpiresAt") Instant claimExpiresAt);

	@Modifying(clearAutomatically = true, flushAutomatically = true)
	@Query("""
			update WorkflowDispatchOutbox e
			set e.status = :sent, e.dispatchedAt = :now, e.lastError = null,
			    e.claimId = null, e.claimExpiresAt = null
			where e.taskId = :taskId and e.status = :claimed and e.claimId = :claimId
			  and e.claimExpiresAt > :now
			""")
	int markSentIfOwned(@Param("taskId") String taskId,
			@Param("claimed") WorkflowDispatchOutbox.DispatchStatus claimed,
			@Param("sent") WorkflowDispatchOutbox.DispatchStatus sent,
			@Param("claimId") String claimId, @Param("now") Instant now);

	@Modifying(clearAutomatically = true, flushAutomatically = true)
	@Query("""
			update WorkflowDispatchOutbox e
			set e.status = :pending, e.attempts = e.attempts + 1,
			    e.lastError = :error, e.nextAttemptAt = :nextAttemptAt,
			    e.claimId = null, e.claimExpiresAt = null
			where e.taskId = :taskId and e.status = :claimed and e.claimId = :claimId
			  and e.claimExpiresAt > :now and e.attempts = :expectedAttempts
			""")
	int markRetryIfOwned(@Param("taskId") String taskId,
			@Param("claimed") WorkflowDispatchOutbox.DispatchStatus claimed,
			@Param("pending") WorkflowDispatchOutbox.DispatchStatus pending,
			@Param("claimId") String claimId, @Param("now") Instant now,
			@Param("expectedAttempts") int expectedAttempts, @Param("error") String error,
			@Param("nextAttemptAt") Instant nextAttemptAt);
}
