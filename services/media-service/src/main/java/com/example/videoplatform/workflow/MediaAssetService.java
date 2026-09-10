package com.example.videoplatform.workflow;

import com.example.videoplatform.transcript.TranscriptResult;
import java.util.Optional;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

/**
 * Media asset operations are always scoped by tenant.  The legacy overloads
 * remain only for old callers/fixtures and resolve to the explicit legacy
 * workspace; workflow code must use the tenant-aware methods.
 */
@Service
public class MediaAssetService {

	private final MediaAssetRepository assetRepository;

	public MediaAssetService(MediaAssetRepository assetRepository) {
		this.assetRepository = assetRepository;
	}

	@Transactional(readOnly = true)
	public Optional<MediaAsset> find(String contentMd5) {
		return find("legacy", contentMd5);
	}

	@Transactional(readOnly = true)
	public Optional<MediaAsset> find(String tenantId, String contentMd5) {
		return assetRepository.findByTenantIdAndContentMd5(normalizeTenantId(tenantId), contentMd5);
	}

	@Transactional(readOnly = true)
	public boolean isReady(String contentMd5) {
		return isReady("legacy", contentMd5);
	}

	@Transactional(readOnly = true)
	public boolean isReady(String tenantId, String contentMd5) {
		return find(tenantId, contentMd5)
				.map(a -> a.getStatus() == MediaAsset.AssetStatus.READY)
				.orElse(false);
	}

	/** Mark (or create) a tenant-scoped asset as processing before long I/O. */
	@Transactional
	public void markProcessing(String contentMd5, String storagePath) {
		markProcessing("legacy", contentMd5, storagePath);
	}

	@Transactional
	public void markProcessing(String tenantId, String contentMd5, String storagePath) {
		String scope = normalizeTenantId(tenantId);
		MediaAsset asset = assetRepository.findByTenantIdAndContentMd5(scope, contentMd5).orElse(null);
		if (asset == null) {
			assetRepository.save(new MediaAsset(scope, contentMd5, storagePath));
		} else {
			asset.setStatus(MediaAsset.AssetStatus.PROCESSING);
		}
	}

	@Transactional
	public void markReady(String contentMd5, TranscriptResult transcript, String summary) {
		markReady("legacy", contentMd5, transcript, summary);
	}

	@Transactional
	public void markReady(String tenantId, String contentMd5, TranscriptResult transcript, String summary) {
		MediaAsset asset = find(tenantId, contentMd5)
				.orElseThrow(() -> new IllegalStateException("资产不存在: " + contentMd5));
		asset.markReady(transcript, summary);
	}

	@Transactional
	public void markFailed(String contentMd5, String errorMessage) {
		markFailed("legacy", contentMd5, errorMessage);
	}

	@Transactional
	public void markFailed(String tenantId, String contentMd5, String errorMessage) {
		find(tenantId, contentMd5).ifPresent(asset -> asset.markFailed(errorMessage));
	}

	private static String normalizeTenantId(String tenantId) {
		return tenantId == null || tenantId.isBlank() ? "legacy" : tenantId.trim();
	}
}
