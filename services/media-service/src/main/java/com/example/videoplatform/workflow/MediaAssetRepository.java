package com.example.videoplatform.workflow;

import jakarta.persistence.LockModeType;
import java.time.Instant;
import java.util.List;
import java.util.Optional;
import org.springframework.data.domain.Pageable;
import org.springframework.data.jpa.repository.JpaRepository;
import org.springframework.data.jpa.repository.Lock;
import org.springframework.data.jpa.repository.Query;
import org.springframework.data.repository.query.Param;
import org.springframework.stereotype.Repository;

@Repository
public interface MediaAssetRepository extends JpaRepository<MediaAsset, String> {

	Optional<MediaAsset> findByTenantIdAndContentMd5(String tenantId, String contentMd5);

	List<MediaAsset> findByStoragePath(String storagePath);

	@Lock(LockModeType.PESSIMISTIC_WRITE)
	@Query("select a from MediaAsset a where a.createdAt < :cutoff and a.transcript is not null "
			+ "order by a.createdAt asc")
	List<MediaAsset> findTranscriptRetentionCandidates(@Param("cutoff") Instant cutoff, Pageable pageable);
}
