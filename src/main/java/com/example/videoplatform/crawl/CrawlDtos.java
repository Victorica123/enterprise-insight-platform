package com.example.videoplatform.crawl;

import jakarta.validation.constraints.NotBlank;
import java.time.Instant;
import java.util.List;
import org.springframework.data.domain.Page;

public final class CrawlDtos {

	private CrawlDtos() {
	}

	public record UpsertCrawledVideoRequest(
			@NotBlank String site,
			@NotBlank String sourceVideoId,
			@NotBlank String title,
			String authorName,
			String authorId,
			String description,
			String pageUrl,
			String coverUrl,
			Long durationSeconds,
			Instant publishedAt,
			Long viewCount,
			Long likeCount,
			Long coinCount,
			Long favoriteCount,
			Long shareCount,
			Long commentCount,
			String tagsJson,
			String rawJson,
			Instant crawledAt) {
	}

	public record CrawledVideoView(
			String id,
			String owner,
			String site,
			String sourceVideoId,
			String title,
			String authorName,
			String authorId,
			String description,
			String pageUrl,
			String coverUrl,
			Long durationSeconds,
			Instant publishedAt,
			Long viewCount,
			Long likeCount,
			Long coinCount,
			Long favoriteCount,
			Long shareCount,
			Long commentCount,
			String tagsJson,
			String rawJson,
			Instant crawledAt,
			Instant createdAt,
			Instant updatedAt) {

		public static CrawledVideoView from(CrawledVideo video) {
			return new CrawledVideoView(
					video.getId(),
					video.getOwner(),
					video.getSite(),
					video.getSourceVideoId(),
					video.getTitle(),
					video.getAuthorName(),
					video.getAuthorId(),
					video.getDescription(),
					video.getPageUrl(),
					video.getCoverUrl(),
					video.getDurationSeconds(),
					video.getPublishedAt(),
					video.getViewCount(),
					video.getLikeCount(),
					video.getCoinCount(),
					video.getFavoriteCount(),
					video.getShareCount(),
					video.getCommentCount(),
					video.getTagsJson(),
					video.getRawJson(),
					video.getCrawledAt(),
					video.getCreatedAt(),
					video.getUpdatedAt());
		}
	}

	public record PageView<T>(
			List<T> content,
			int page,
			int size,
			long totalElements,
			int totalPages) {

		public static <T> PageView<T> from(Page<T> page) {
			return new PageView<>(
					page.getContent(),
					page.getNumber(),
					page.getSize(),
					page.getTotalElements(),
					page.getTotalPages());
		}
	}
}
