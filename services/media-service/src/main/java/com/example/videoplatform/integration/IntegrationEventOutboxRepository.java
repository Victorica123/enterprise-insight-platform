package com.example.videoplatform.integration;

import java.time.Instant;
import java.util.List;
import org.springframework.data.jpa.repository.JpaRepository;

public interface IntegrationEventOutboxRepository extends JpaRepository<IntegrationEventOutbox, String> {

	List<IntegrationEventOutbox> findTop50ByStatusAndNextAttemptAtLessThanEqualOrderByCreatedAt(
			IntegrationEventOutbox.DeliveryStatus status, Instant now);
}
