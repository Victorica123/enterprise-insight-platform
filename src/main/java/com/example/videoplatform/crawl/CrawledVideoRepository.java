package com.example.videoplatform.crawl;

import java.util.Optional;
import org.springframework.data.domain.Page;
import org.springframework.data.domain.Pageable;
import org.springframework.data.jpa.repository.JpaRepository;
import org.springframework.stereotype.Repository;

@Repository
public interface CrawledVideoRepository extends JpaRepository<CrawledVideo, String> {

	Optional<CrawledVideo> findByOwnerAndSiteAndSourceVideoId(String owner, String site, String sourceVideoId);

	Optional<CrawledVideo> findByIdAndOwner(String id, String owner);

	Page<CrawledVideo> findByOwnerOrderByCrawledAtDesc(String owner, Pageable pageable);

	Page<CrawledVideo> findByOwnerAndSiteOrderByCrawledAtDesc(String owner, String site, Pageable pageable);
}
