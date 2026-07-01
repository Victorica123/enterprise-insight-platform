package com.example.videoplatform.crawl;

import org.springframework.data.domain.Page;
import org.springframework.data.domain.PageRequest;
import org.springframework.data.domain.Pageable;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;
import org.springframework.util.StringUtils;

@Service
public class CrawledVideoService {

	private final CrawledVideoRepository repository;

	public CrawledVideoService(CrawledVideoRepository repository) {
		this.repository = repository;
	}

	@Transactional
	public CrawledVideo upsert(String owner, CrawlDtos.UpsertCrawledVideoRequest request) {
		String site = normalizeSite(request.site());
		CrawlDtos.UpsertCrawledVideoRequest normalized = new CrawlDtos.UpsertCrawledVideoRequest(
				site,
				request.sourceVideoId(),
				request.title(),
				request.authorName(),
				request.authorId(),
				request.description(),
				request.pageUrl(),
				request.coverUrl(),
				request.durationSeconds(),
				request.publishedAt(),
				request.viewCount(),
				request.likeCount(),
				request.coinCount(),
				request.favoriteCount(),
				request.shareCount(),
				request.commentCount(),
				request.tagsJson(),
				request.rawJson(),
				request.crawledAt());

		CrawledVideo video = repository.findByOwnerAndSiteAndSourceVideoId(owner, site, request.sourceVideoId())
				.orElseGet(() -> new CrawledVideo(owner, normalized));
		video.apply(normalized);
		return repository.save(video);
	}

	@Transactional(readOnly = true)
	public Page<CrawledVideo> list(String owner, String site, int page, int size) {
		Pageable pageable = PageRequest.of(Math.max(page, 0), Math.min(Math.max(size, 1), 100));
		if (StringUtils.hasText(site)) {
			return repository.findByOwnerAndSiteOrderByCrawledAtDesc(owner, normalizeSite(site), pageable);
		}
		return repository.findByOwnerOrderByCrawledAtDesc(owner, pageable);
	}

	@Transactional(readOnly = true)
	public CrawledVideo require(String owner, String id) {
		return repository.findByIdAndOwner(id, owner)
				.orElseThrow(() -> new IllegalArgumentException("爬取视频数据不存在或无权访问"));
	}

	private String normalizeSite(String site) {
		if (!StringUtils.hasText(site)) {
			throw new IllegalArgumentException("site must not be blank");
		}
		return site.trim().toLowerCase();
	}
}
