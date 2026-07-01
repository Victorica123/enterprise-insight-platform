package com.example.videoplatform.crawl;

import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.Id;
import jakarta.persistence.Table;
import java.time.Instant;
import java.util.UUID;

@Entity
@Table(name = "crawled_video")
public class CrawledVideo {

	@Id
	private String id;

	private String owner;

	private String site;

	private String sourceVideoId;

	private String title;

	private String authorName;

	private String authorId;

	@Column(length = 5000)
	private String description;

	@Column(length = 1000)
	private String pageUrl;

	@Column(length = 1000)
	private String coverUrl;

	private Long durationSeconds;

	private Instant publishedAt;

	private Long viewCount;

	private Long likeCount;

	private Long coinCount;

	private Long favoriteCount;

	private Long shareCount;

	private Long commentCount;

	@Column(columnDefinition = "TEXT")
	private String tagsJson;

	@Column(columnDefinition = "TEXT")
	private String rawJson;

	private Instant crawledAt;

	private Instant createdAt;

	private Instant updatedAt;

	protected CrawledVideo() {
		// JPA requires no-arg constructor
	}

	public CrawledVideo(String owner, CrawlDtos.UpsertCrawledVideoRequest request) {
		this.id = UUID.randomUUID().toString();
		this.owner = owner;
		this.createdAt = Instant.now();
		apply(request);
	}

	public void apply(CrawlDtos.UpsertCrawledVideoRequest request) {
		this.site = request.site();
		this.sourceVideoId = request.sourceVideoId();
		this.title = request.title();
		this.authorName = request.authorName();
		this.authorId = request.authorId();
		this.description = request.description();
		this.pageUrl = request.pageUrl();
		this.coverUrl = request.coverUrl();
		this.durationSeconds = request.durationSeconds();
		this.publishedAt = request.publishedAt();
		this.viewCount = request.viewCount();
		this.likeCount = request.likeCount();
		this.coinCount = request.coinCount();
		this.favoriteCount = request.favoriteCount();
		this.shareCount = request.shareCount();
		this.commentCount = request.commentCount();
		this.tagsJson = request.tagsJson();
		this.rawJson = request.rawJson();
		this.crawledAt = request.crawledAt() == null ? Instant.now() : request.crawledAt();
		this.updatedAt = Instant.now();
	}

	public String getId() {
		return id;
	}

	public String getOwner() {
		return owner;
	}

	public String getSite() {
		return site;
	}

	public String getSourceVideoId() {
		return sourceVideoId;
	}

	public String getTitle() {
		return title;
	}

	public String getAuthorName() {
		return authorName;
	}

	public String getAuthorId() {
		return authorId;
	}

	public String getDescription() {
		return description;
	}

	public String getPageUrl() {
		return pageUrl;
	}

	public String getCoverUrl() {
		return coverUrl;
	}

	public Long getDurationSeconds() {
		return durationSeconds;
	}

	public Instant getPublishedAt() {
		return publishedAt;
	}

	public Long getViewCount() {
		return viewCount;
	}

	public Long getLikeCount() {
		return likeCount;
	}

	public Long getCoinCount() {
		return coinCount;
	}

	public Long getFavoriteCount() {
		return favoriteCount;
	}

	public Long getShareCount() {
		return shareCount;
	}

	public Long getCommentCount() {
		return commentCount;
	}

	public String getTagsJson() {
		return tagsJson;
	}

	public String getRawJson() {
		return rawJson;
	}

	public Instant getCrawledAt() {
		return crawledAt;
	}

	public Instant getCreatedAt() {
		return createdAt;
	}

	public Instant getUpdatedAt() {
		return updatedAt;
	}
}
