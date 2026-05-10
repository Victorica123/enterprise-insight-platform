package com.example.videoplatform.auth;

import jakarta.validation.constraints.NotBlank;

public final class AuthDtos {

	private AuthDtos() {
	}

	public record RegisterRequest(@NotBlank String username, @NotBlank String password) {
	}

	public record LoginRequest(@NotBlank String username, @NotBlank String password) {
	}

	public record AuthResponse(String userId, String username, String token) {
	}
}
