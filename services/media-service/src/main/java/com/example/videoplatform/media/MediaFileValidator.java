package com.example.videoplatform.media;

import java.io.IOException;
import java.io.InputStream;
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
		String safeName = safeVideoFileName(file.getOriginalFilename());
		String contentType = file.getContentType();
		if (contentType != null && !contentType.isBlank() && !contentType.toLowerCase().startsWith("video/")) {
			throw new IllegalArgumentException("Uploaded file content type must be video/*");
		}
		try (InputStream input = file.getInputStream()) {
			byte[] header = input.readNBytes(12);
			if (!matchesContainer(safeName, header)) {
				throw new IllegalArgumentException("Uploaded file content does not match its video extension");
			}
		} catch (IOException exception) {
			throw new IllegalArgumentException("Unable to inspect uploaded file", exception);
		}
	}

	private static boolean matchesContainer(String fileName, byte[] header) {
		String lower = fileName.toLowerCase();
		if (lower.endsWith(".mp4") || lower.endsWith(".mov") || lower.endsWith(".m4v")) {
			return header.length >= 8 && header[4] == 'f' && header[5] == 't'
					&& header[6] == 'y' && header[7] == 'p';
		}
		if (lower.endsWith(".avi")) {
			return header.length >= 12 && header[0] == 'R' && header[1] == 'I'
					&& header[2] == 'F' && header[3] == 'F'
					&& header[8] == 'A' && header[9] == 'V'
					&& header[10] == 'I';
		}
		// Matroska/WebM share the EBML container signature.
		return header.length >= 4 && (header[0] & 0xff) == 0x1a
				&& (header[1] & 0xff) == 0x45 && (header[2] & 0xff) == 0xdf
				&& (header[3] & 0xff) == 0xa3;
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
