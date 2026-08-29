package com.example.videoplatform.auth;

import java.util.UUID;
import org.springframework.stereotype.Service;

@Service
public class WorkspaceService {

	private final WorkspaceRepository workspaceRepository;
	private final WorkspaceMemberRepository memberRepository;

	public WorkspaceService(WorkspaceRepository workspaceRepository, WorkspaceMemberRepository memberRepository) {
		this.workspaceRepository = workspaceRepository;
		this.memberRepository = memberRepository;
	}

	/** Idempotently creates or repairs the user's personal workspace membership. */
	public WorkspaceContext ensurePersonalWorkspace(UserAccount user) {
		String tenantId = user.getPrimaryTenantId();
		if (tenantId == null || tenantId.isBlank()) {
			tenantId = UUID.randomUUID().toString();
			workspaceRepository.save(new Workspace(tenantId, personalWorkspaceName(user.getUsername()), user.getUserId()));
			user.setPrimaryTenantId(tenantId);
		} else if (!workspaceRepository.existsById(tenantId)) {
			workspaceRepository.save(new Workspace(tenantId, personalWorkspaceName(user.getUsername()), user.getUserId()));
		}

		String resolvedTenantId = tenantId;
		WorkspaceMember member = memberRepository.findByTenantIdAndUserId(resolvedTenantId, user.getUserId())
				.orElseGet(() -> memberRepository.save(new WorkspaceMember(
						UUID.randomUUID().toString(), resolvedTenantId, user.getUserId(), WorkspaceMember.WorkspaceRole.OWNER)));
		return new WorkspaceContext(resolvedTenantId, member.getRole().jwtRole(), "personal");
	}

	private static String personalWorkspaceName(String username) {
		String suffix = " 的工作区";
		int maxUsernameLength = Math.max(1, 100 - suffix.length());
		String safeUsername = username.length() > maxUsernameLength
				? username.substring(0, maxUsernameLength)
				: username;
		return safeUsername + suffix;
	}

	public record WorkspaceContext(String tenantId, String jwtRole, String workspaceType) {
	}
}
