package com.example.videoplatform.crawl;

import com.example.videoplatform.common.ApiResponse;
import jakarta.validation.Valid;
import org.springframework.data.domain.Page;
import org.springframework.security.core.Authentication;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/api/crawled-videos")
public class CrawledVideoController {

	private final CrawledVideoService service;

	public CrawledVideoController(CrawledVideoService service) {
		this.service = service;
	}

	@PostMapping
	public ApiResponse<CrawlDtos.CrawledVideoView> upsert(Authentication authentication,
			@Valid @RequestBody CrawlDtos.UpsertCrawledVideoRequest request) {
		return ApiResponse.ok(CrawlDtos.CrawledVideoView.from(service.upsert(authentication.getName(), request)));
	}

	@GetMapping
	public ApiResponse<CrawlDtos.PageView<CrawlDtos.CrawledVideoView>> list(Authentication authentication,
			@RequestParam(required = false) String site,
			@RequestParam(defaultValue = "0") int page,
			@RequestParam(defaultValue = "20") int size) {
		Page<CrawlDtos.CrawledVideoView> videos = service.list(authentication.getName(), site, page, size)
				.map(CrawlDtos.CrawledVideoView::from);
		return ApiResponse.ok(CrawlDtos.PageView.from(videos));
	}

	@GetMapping("/{id}")
	public ApiResponse<CrawlDtos.CrawledVideoView> get(Authentication authentication, @PathVariable String id) {
		return ApiResponse.ok(CrawlDtos.CrawledVideoView.from(service.require(authentication.getName(), id)));
	}
}
