package com.example.videoplatform.common;

public class StringUtils {

	private StringUtils() {
	}

	public static boolean isBlank(String value) {
		return value == null || value.trim().isEmpty();
	}

	public static String trimTrailingSlash(String value) {
		return value.endsWith("/") ? value.substring(0, value.length() - 1) : value;
	}
}
