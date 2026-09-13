package com.example.videoplatform.integration;

import java.time.Instant;
import java.util.List;
import org.springframework.data.jpa.repository.JpaRepository;
import org.springframework.data.jpa.repository.Modifying;
import org.springframework.data.jpa.repository.Query;
import org.springframework.data.repository.query.Param;

public interface IntegrationEventOutboxRepository extends JpaRepository<IntegrationEventOutbox, String> {

	@Modifying(clearAutomatically = true, flushAutomatically = true)
	@Query("update IntegrationEventOutbox e set e.status = com.example.videoplatform.integration.IntegrationEventOutbox.DeliveryStatus.PENDING, "
			+ "e.nextAttemptAt = :retryAt, e.claimId = null, e.claimExpiresAt = null "
			+ "where e.eventId = :eventId and e.claimId = :claimId and e.claimExpiresAt > :now "
			+ "and e.status = com.example.videoplatform.integration.IntegrationEventOutbox.DeliveryStatus.CLAIMED")
	int deferIfOwned(@Param("eventId") String eventId, @Param("claimId") String claimId,
			@Param("now") Instant now, @Param("retryAt") Instant retryAt);

	List<IntegrationEventOutbox> findTop50ByStatusAndNextAttemptAtLessThanEqualOrderByCreatedAt(
			IntegrationEventOutbox.DeliveryStatus status, Instant now);

	List<IntegrationEventOutbox> findTop50ByStatusAndClaimExpiresAtLessThanEqualOrderByCreatedAt(
			IntegrationEventOutbox.DeliveryStatus status, Instant now);

	/** Claim is deliberately conditional so two dispatcher instances cannot own the same row. */
	@Modifying(clearAutomatically = true, flushAutomatically = true)
	@Query("""
			update IntegrationEventOutbox e
			set e.status = :claimedStatus, e.claimId = :claimId, e.claimExpiresAt = :claimExpiresAt
			where e.eventId = :eventId
			  and ((e.status = :pendingStatus and e.nextAttemptAt <= :now)
			       or (e.status = :claimedStatus and e.claimExpiresAt <= :now))
			""")
	int claimIfAvailable(
			@Param("eventId") String eventId,
			@Param("pendingStatus") IntegrationEventOutbox.DeliveryStatus pendingStatus,
			@Param("claimedStatus") IntegrationEventOutbox.DeliveryStatus claimedStatus,
			@Param("now") Instant now,
			@Param("claimId") String claimId,
			@Param("claimExpiresAt") Instant claimExpiresAt);

	@Modifying(clearAutomatically = true, flushAutomatically = true)
	@Query("""
			update IntegrationEventOutbox e
			set e.status = :sentStatus, e.publishedAt = :publishedAt,
			    e.lastError = null, e.claimId = null, e.claimExpiresAt = null
			where e.eventId = :eventId and e.status = :claimedStatus
			  and e.claimId = :claimId and e.claimExpiresAt > :now
			""")
	int markSentIfOwned(
			@Param("eventId") String eventId,
			@Param("claimedStatus") IntegrationEventOutbox.DeliveryStatus claimedStatus,
			@Param("sentStatus") IntegrationEventOutbox.DeliveryStatus sentStatus,
			@Param("claimId") String claimId,
			@Param("now") Instant now,
			@Param("publishedAt") Instant publishedAt);

	@Modifying(clearAutomatically = true, flushAutomatically = true)
	@Query("""
			update IntegrationEventOutbox e
			set e.status = :nextStatus, e.attempts = e.attempts + 1,
			    e.lastError = :error, e.nextAttemptAt = :nextAttemptAt,
			    e.claimId = null, e.claimExpiresAt = null
			where e.eventId = :eventId and e.status = :claimedStatus
			  and e.claimId = :claimId and e.claimExpiresAt > :now
			  and e.attempts = :expectedAttempts
			""")
	int markFailedIfOwned(
			@Param("eventId") String eventId,
			@Param("claimedStatus") IntegrationEventOutbox.DeliveryStatus claimedStatus,
			@Param("nextStatus") IntegrationEventOutbox.DeliveryStatus nextStatus,
			@Param("claimId") String claimId,
			@Param("now") Instant now,
			@Param("expectedAttempts") int expectedAttempts,
			@Param("error") String error,
			@Param("nextAttemptAt") Instant nextAttemptAt);
}
