package com.example.videoplatform.workflow;

import java.util.Optional;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

/**
 * 媒体资产的短事务操作。与 {@link VideoTaskService} 一样，每个方法一个独立事务，
 * 避免在 FFmpeg / Whisper / LLM 外部 I/O 期间长时间占用数据库连接。
 */
@Service
public class MediaAssetService {

	private final MediaAssetRepository assetRepository;

	public MediaAssetService(MediaAssetRepository assetRepository) {
		this.assetRepository = assetRepository;
	}

	@Transactional(readOnly = true)
	public Optional<MediaAsset> find(String contentMd5) {
		return assetRepository.findById(contentMd5);
	}

	@Transactional(readOnly = true)
	public boolean isReady(String contentMd5) {
		return assetRepository.findById(contentMd5)
				.map(a -> a.getStatus() == MediaAsset.AssetStatus.READY)
				.orElse(false);
	}

	/** 标记（或创建）资产为处理中。单飞的赢家在开始长处理前调用。 */
	@Transactional
	public void markProcessing(String contentMd5, String storagePath) {
		MediaAsset asset = assetRepository.findById(contentMd5).orElse(null);
		if (asset == null) {
			assetRepository.save(new MediaAsset(contentMd5, storagePath));
		} else {
			asset.setStatus(MediaAsset.AssetStatus.PROCESSING);
		}
	}

	@Transactional
	public void markReady(String contentMd5, String transcript, String summary) {
		MediaAsset asset = assetRepository.findById(contentMd5)
				.orElseThrow(() -> new IllegalStateException("资产不存在: " + contentMd5));
		asset.markReady(transcript, summary);
	}

	@Transactional
	public void markFailed(String contentMd5, String errorMessage) {
		assetRepository.findById(contentMd5).ifPresent(asset -> asset.markFailed(errorMessage));
	}
}
