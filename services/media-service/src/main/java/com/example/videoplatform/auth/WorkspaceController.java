package com.example.videoplatform.auth;

import com.example.videoplatform.common.ApiResponse;
import jakarta.validation.Valid;
import java.util.List;
import org.springframework.security.core.Authentication;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PatchMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/api/workspaces")
public class WorkspaceController {

	private final WorkspaceCollaborationService collaborationService;
	private final AuthService authService;

	public WorkspaceController(WorkspaceCollaborationService collaborationService, AuthService authService) {
		this.collaborationService = collaborationService;
		this.authService = authService;
	}

	@GetMapping
	public ApiResponse<List<WorkspaceDtos.WorkspaceSummary>> list(Authentication authentication) {
		return ApiResponse.ok(collaborationService.listWorkspaces(WorkspacePrincipal.require(authentication).userId()));
	}

	@PostMapping
	public ApiResponse<WorkspaceDtos.WorkspaceSummary> create(
			Authentication authentication, @Valid @RequestBody WorkspaceDtos.CreateWorkspaceRequest request) {
		return ApiResponse.ok(collaborationService.createTeam(
				WorkspacePrincipal.require(authentication).userId(), request.name()));
	}

	@GetMapping("/{tenantId}/members")
	public ApiResponse<List<WorkspaceDtos.MemberView>> members(
			Authentication authentication, @PathVariable String tenantId) {
		return ApiResponse.ok(collaborationService.listMembers(
				WorkspacePrincipal.require(authentication).userId(), tenantId));
	}

	@PostMapping("/{tenantId}/invitations")
	public ApiResponse<WorkspaceDtos.InvitationResponse> invite(
			Authentication authentication, @PathVariable String tenantId) {
		return ApiResponse.ok(collaborationService.createInvitation(
				WorkspacePrincipal.require(authentication).userId(), tenantId));
	}

	@PostMapping("/invitations/accept")
	public ApiResponse<WorkspaceDtos.WorkspaceSummary> accept(
			Authentication authentication, @Valid @RequestBody WorkspaceDtos.AcceptInvitationRequest request) {
		return ApiResponse.ok(collaborationService.acceptInvitation(
				WorkspacePrincipal.require(authentication).userId(), request.invitationCode()));
	}

	@PatchMapping("/{tenantId}/members/{userId}")
	public ApiResponse<WorkspaceDtos.MemberView> updateRole(
			Authentication authentication, @PathVariable String tenantId, @PathVariable String userId,
			@Valid @RequestBody WorkspaceDtos.UpdateMemberRoleRequest request) {
		return ApiResponse.ok(collaborationService.updateMemberRole(
				WorkspacePrincipal.require(authentication).userId(), tenantId, userId, request.role()));
	}

	@PostMapping("/{tenantId}/switch")
	public ApiResponse<AuthDtos.AuthResponse> switchWorkspace(
			Authentication authentication, @PathVariable String tenantId) {
		return ApiResponse.ok(authService.switchWorkspace(
				WorkspacePrincipal.require(authentication).userId(), tenantId));
	}
}
