package com.example.videoplatform.config;

import java.time.Duration;
import org.springframework.boot.context.properties.ConfigurationProperties;

@ConfigurationProperties(prefix = "app.storage")
public class StorageProperties {
	private String basePath;
	private String type = "local";
	private final S3 s3 = new S3();
	private final Cleanup cleanup = new Cleanup();

	public String getBasePath() {
		return basePath;
	}

	public void setBasePath(String basePath) {
		this.basePath = basePath;
	}

	public String getType() {
		return type;
	}

	public void setType(String type) {
		this.type = type;
	}

	public S3 getS3() {
		return s3;
	}

	public Cleanup getCleanup() {
		return cleanup;
	}

	public static class Cleanup {
		private Duration chunkRetention = Duration.ofHours(24);

		public Duration getChunkRetention() {
			return chunkRetention;
		}

		public void setChunkRetention(Duration chunkRetention) {
			this.chunkRetention = chunkRetention;
		}
	}

	public static class S3 {
		private String endpoint;
		private String publicEndpoint;
		private String region = "us-east-1";
		private String bucket = "video-platform";
		private String accessKey;
		private String secretKey;
		private boolean pathStyleAccess = true;

		public String getEndpoint() {
			return endpoint;
		}

		public void setEndpoint(String endpoint) {
			this.endpoint = endpoint;
		}

		public String getPublicEndpoint() {
			return publicEndpoint;
		}

		public void setPublicEndpoint(String publicEndpoint) {
			this.publicEndpoint = publicEndpoint;
		}

		public String getRegion() {
			return region;
		}

		public void setRegion(String region) {
			this.region = region;
		}

		public String getBucket() {
			return bucket;
		}

		public void setBucket(String bucket) {
			this.bucket = bucket;
		}

		public String getAccessKey() {
			return accessKey;
		}

		public void setAccessKey(String accessKey) {
			this.accessKey = accessKey;
		}

		public String getSecretKey() {
			return secretKey;
		}

		public void setSecretKey(String secretKey) {
			this.secretKey = secretKey;
		}

		public boolean isPathStyleAccess() {
			return pathStyleAccess;
		}

		public void setPathStyleAccess(boolean pathStyleAccess) {
			this.pathStyleAccess = pathStyleAccess;
		}
	}
}
