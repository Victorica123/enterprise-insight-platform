package com.example.videoplatform.media;

import org.springframework.web.multipart.MultipartFile;

final class MediaFileValidator {

	private MediaFileValidator() {
	}

	static String safeVideoFileName(String originalName) {
		String fileName = originalName == null || originalName.isBlank() ? "video.mp4" : originalName;
		String safeName = fileName.replaceAll("[^a-zA-Z0-9._-]", "_");
		if (!hasVideoExtension(safeName)) {
			throw new IllegalArgumentException("Only video files are supported");
		}
		return safeName;
	}

	static void requireVideoFile(MultipartFile file) {
		if (file == null || file.isEmpty()) {
			throw new IllegalArgumentException("Uploaded file must not be empty");
		}
		safeVideoFileName(file.getOriginalFilename());
		String contentType = file.getContentType();
		if (contentType != null && !contentType.isBlank() && !contentType.toLowerCase().startsWith("video/")) {
			throw new IllegalArgumentException("Uploaded file content type must be video/*");
		}
	}

	private static boolean hasVideoExtension(String fileName) {
		String lower = fileName.toLowerCase();
		return lower.endsWith(".mp4")
				|| lower.endsWith(".mov")
				|| lower.endsWith(".m4v")
				|| lower.endsWith(".avi")
				|| lower.endsWith(".mkv")
				|| lower.endsWith(".webm");
	}
}
