package com.example.videoplatform.auth;

import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.Size;

public final class AuthDtos {

	private AuthDtos() {
	}

	// BCrypt 有效输入上限 72 字节；下限 8 与前端 minlength 保持一致
	public record RegisterRequest(
			@NotBlank @Size(max = 50) String username,
			@NotBlank @Size(min = 8, max = 72) String password) {
	}

	public record LoginRequest(
			@NotBlank @Size(max = 50) String username,
			@NotBlank @Size(max = 72) String password) {
	}

	public record AuthResponse(String userId, String username, String token) {
	}
}
