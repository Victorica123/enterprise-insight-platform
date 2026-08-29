package com.example.videoplatform.auth;

import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotNull;
import jakarta.validation.constraints.Size;
import java.time.Instant;

public final class WorkspaceDtos {

	private WorkspaceDtos() {
	}

	public record CreateWorkspaceRequest(@NotBlank @Size(max = 100) String name) {
	}

	public record AcceptInvitationRequest(@NotBlank @Size(min = 32, max = 200) String invitationCode) {
	}

	public record UpdateMemberRoleRequest(@NotNull WorkspaceMember.WorkspaceRole role) {
	}

	public record WorkspaceSummary(
			String tenantId, String name, String workspaceType,
			WorkspaceMember.WorkspaceRole role, String jwtRole,
			String createdBy, Instant createdAt, Instant joinedAt) {
	}

	public record MemberView(
			String userId, String username, WorkspaceMember.WorkspaceRole role,
			String jwtRole, Instant joinedAt) {
	}

	public record InvitationResponse(
			String invitationCode, String tenantId, String workspaceName, Instant expiresAt) {
	}
}
