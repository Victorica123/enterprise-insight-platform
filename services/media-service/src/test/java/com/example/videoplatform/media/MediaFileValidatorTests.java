package com.example.videoplatform.media;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;

import org.junit.jupiter.api.Test;
import org.springframework.mock.web.MockMultipartFile;

class MediaFileValidatorTests {

	@Test
	void acceptsVideoFiles() {
		MockMultipartFile file = new MockMultipartFile("file", "Demo.MP4", "video/mp4", mp4Header());

		MediaFileValidator.requireVideoFile(file);

		assertThat(MediaFileValidator.safeVideoFileName("Demo.MP4")).isEqualTo("Demo.MP4");
	}

	@Test
	void rejectsNonVideoExtensions() {
		MockMultipartFile file = new MockMultipartFile("file", "pom.xml", "text/xml", new byte[] {1});

		assertThatThrownBy(() -> MediaFileValidator.requireVideoFile(file))
				.isInstanceOf(IllegalArgumentException.class)
				.hasMessageContaining("Only video files");
	}

	@Test
	void sanitizesUnsafeFileNameCharacters() {
		assertThat(MediaFileValidator.safeVideoFileName("../demo video(1).webm"))
				.isEqualTo(".._demo_video_1_.webm");
	}

	@Test
	void defaultsBlankFileNameToVideoMp4() {
		assertThat(MediaFileValidator.safeVideoFileName(" "))
				.isEqualTo("video.mp4");
	}

	@Test
	void rejectsNonVideoContentTypeWhenPresent() {
		MockMultipartFile file = new MockMultipartFile("file", "demo.mp4", "application/octet-stream",
				mp4Header());

		assertThatThrownBy(() -> MediaFileValidator.requireVideoFile(file))
				.isInstanceOf(IllegalArgumentException.class)
				.hasMessageContaining("content type");
	}

	@Test
	void rejectsVideoExtensionWithUnrecognizedContainerHeader() {
		MockMultipartFile file = new MockMultipartFile("file", "demo.mp4", "video/mp4", new byte[] {1, 2, 3});

		assertThatThrownBy(() -> MediaFileValidator.requireVideoFile(file))
				.isInstanceOf(IllegalArgumentException.class)
				.hasMessageContaining("does not match");
	}

	private static byte[] mp4Header() {
		return new byte[] {0, 0, 0, 24, 'f', 't', 'y', 'p', 'i', 's', 'o', 'm'};
	}
}
