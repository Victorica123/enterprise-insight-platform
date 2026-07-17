package com.example.videoplatform.media;

import static org.assertj.core.api.Assertions.assertThat;

import com.example.videoplatform.config.AppProperties;
import java.time.Duration;
import org.junit.jupiter.api.Test;

class S3MediaStorageServiceTests {

	@Test
	void directUploadUrlUsesPublicEndpointWhenConfigured() {
		AppProperties properties = s3Properties("http://minio:9000", "https://files.example.com");
		S3MediaStorageService service = new S3MediaStorageService(properties);

		MediaStorageService.DirectUploadTarget target = service.createDirectUploadTarget("demo.mp4",
				Duration.ofMinutes(15));

		assertThat(target.storagePath()).startsWith("s3://video-platform/uploads/direct/");
		assertThat(target.uploadUrl()).startsWith("https://files.example.com/video-platform/uploads/direct/");
		assertThat(target.uploadUrl()).contains("X-Amz-Signature=");
	}

	@Test
	void directUploadUrlFallsBackToInternalEndpointWhenPublicEndpointIsBlank() {
		AppProperties properties = s3Properties("http://minio:9000", "");
		S3MediaStorageService service = new S3MediaStorageService(properties);

		MediaStorageService.DirectUploadTarget target = service.createDirectUploadTarget("demo.mp4",
				Duration.ofMinutes(15));

		assertThat(target.uploadUrl()).startsWith("http://minio:9000/video-platform/uploads/direct/");
	}

	private AppProperties s3Properties(String endpoint, String publicEndpoint) {
		AppProperties properties = new AppProperties();
		properties.getStorage().setType("s3");
		properties.getStorage().getS3().setEndpoint(endpoint);
		properties.getStorage().getS3().setPublicEndpoint(publicEndpoint);
		properties.getStorage().getS3().setBucket("video-platform");
		properties.getStorage().getS3().setAccessKey("minioadmin");
		properties.getStorage().getS3().setSecretKey("minioadmin123");
		properties.getStorage().getS3().setRegion("us-east-1");
		properties.getStorage().getS3().setPathStyleAccess(true);
		return properties;
	}
}
