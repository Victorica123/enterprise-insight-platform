package com.example.videoplatform.auth;

import java.security.Principal;
import org.springframework.http.HttpStatus;
import org.springframework.security.core.Authentication;
import org.springframework.web.server.ResponseStatusException;

/** Trusted active-Workspace identity reconstructed exclusively from a verified JWT. */
public record WorkspacePrincipal(
		String userId, String username, String tenantId, String role, String workspaceType) implements Principal {

	@Override
	public String getName() {
		return userId;
	}

	public boolean isTeam() {
		return "team".equals(workspaceType);
	}

	public boolean canWrite() {
		return "operator".equals(role) || "admin".equals(role);
	}

	public static WorkspacePrincipal require(Authentication authentication) {
		if (authentication == null || !authentication.isAuthenticated()
				|| !(authentication.getPrincipal() instanceof WorkspacePrincipal principal)) {
			throw new ResponseStatusException(HttpStatus.UNAUTHORIZED, "用户未登录");
		}
		return principal;
	}
}
