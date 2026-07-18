package com.example.videoplatform.workflow;

import java.time.Instant;
import java.util.List;
import org.springframework.data.jpa.repository.JpaRepository;

public interface MediaCleanupJobRepository extends JpaRepository<MediaCleanupJob, String> {

	List<MediaCleanupJob> findTop50ByNextAttemptAtBeforeOrderByCreatedAtAsc(Instant now);
}
