package com.example.videoplatform.config;

import org.springframework.boot.context.properties.ConfigurationProperties;

@ConfigurationProperties(prefix = "app.retention")
public class RetentionProperties extends FeatureProperties {
	private int mediaDays = 30;
	private int transcriptDays = 180;
	private int auditDays = 365;
	private int batchSize = 200;

	public int getMediaDays() {
		return mediaDays;
	}

	public void setMediaDays(int mediaDays) {
		this.mediaDays = mediaDays;
	}

	public int getTranscriptDays() {
		return transcriptDays;
	}

	public void setTranscriptDays(int transcriptDays) {
		this.transcriptDays = transcriptDays;
	}

	public int getAuditDays() {
		return auditDays;
	}

	public void setAuditDays(int auditDays) {
		this.auditDays = auditDays;
	}

	public int getBatchSize() {
		return batchSize;
	}

	public void setBatchSize(int batchSize) {
		this.batchSize = batchSize;
	}
}
