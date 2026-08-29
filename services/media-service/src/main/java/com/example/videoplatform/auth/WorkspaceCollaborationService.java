package com.example.videoplatform.auth;

import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;
import java.security.NoSuchAlgorithmException;
import java.security.SecureRandom;
import java.time.Duration;
import java.time.Instant;
import java.util.Base64;
import java.util.Comparator;
import java.util.List;
import java.util.Map;
import java.util.UUID;
import java.util.function.Function;
import java.util.stream.Collectors;
import org.springframework.http.HttpStatus;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;
import org.springframework.web.server.ResponseStatusException;

@Service
public class WorkspaceCollaborationService {

	private static final Duration INVITATION_TTL = Duration.ofMinutes(15);
	private static final SecureRandom SECURE_RANDOM = new SecureRandom();

	private final WorkspaceRepository workspaceRepository;
	private final WorkspaceMemberRepository memberRepository;
	private final WorkspaceInvitationRepository invitationRepository;
	private final UserAccountRepository userRepository;

	public WorkspaceCollaborationService(
			WorkspaceRepository workspaceRepository,
			WorkspaceMemberRepository memberRepository,
			WorkspaceInvitationRepository invitationRepository,
			UserAccountRepository userRepository) {
		this.workspaceRepository = workspaceRepository;
		this.memberRepository = memberRepository;
		this.invitationRepository = invitationRepository;
		this.userRepository = userRepository;
	}

	@Transactional
	public WorkspaceDtos.WorkspaceSummary createTeam(String userId, String rawName) {
		UserAccount user = requireUser(userId);
		String name = rawName == null ? "" : rawName.trim();
		if (name.isEmpty()) {
			throw new ResponseStatusException(HttpStatus.BAD_REQUEST, "工作区名称不能为空");
		}
		String tenantId = UUID.randomUUID().toString();
		Workspace workspace = workspaceRepository.save(new Workspace(
				tenantId, name, userId, Workspace.WorkspaceType.TEAM));
		WorkspaceMember member = memberRepository.save(new WorkspaceMember(
				UUID.randomUUID().toString(), tenantId, userId, WorkspaceMember.WorkspaceRole.OWNER));
		return summary(workspace, member);
	}

	@Transactional(readOnly = true)
	public List<WorkspaceDtos.WorkspaceSummary> listWorkspaces(String userId) {
		requireUser(userId);
		return memberRepository.findAllByUserIdOrderByJoinedAtAsc(userId).stream()
				.map(member -> summary(requireWorkspace(member.getTenantId()), member))
				.sorted(Comparator.comparing(WorkspaceDtos.WorkspaceSummary::createdAt))
				.toList();
	}

	@Transactional(readOnly = true)
	public List<WorkspaceDtos.MemberView> listMembers(String actorId, String tenantId) {
		requireMembership(tenantId, actorId);
		List<WorkspaceMember> members = memberRepository.findAllByTenantIdOrderByJoinedAtAsc(tenantId);
		Map<String, UserAccount> users = userRepository.findAllById(
				members.stream().map(WorkspaceMember::getUserId).toList()).stream()
				.collect(Collectors.toMap(UserAccount::getUserId, Function.identity()));
		return members.stream().map(member -> {
			UserAccount user = users.get(member.getUserId());
			return new WorkspaceDtos.MemberView(
					member.getUserId(), user == null ? "unknown" : user.getUsername(),
					member.getRole(), member.getRole().jwtRole(), member.getJoinedAt());
		}).toList();
	}

	@Transactional
	public WorkspaceDtos.InvitationResponse createInvitation(String actorId, String tenantId) {
		Workspace workspace = requireWorkspace(tenantId);
		if (workspace.getWorkspaceType() != Workspace.WorkspaceType.TEAM) {
			throw new ResponseStatusException(HttpStatus.CONFLICT, "个人工作区不能创建团队邀请");
		}
		WorkspaceMember actor = requireMembership(tenantId, actorId);
		if (actor.getRole() != WorkspaceMember.WorkspaceRole.OWNER
				&& actor.getRole() != WorkspaceMember.WorkspaceRole.ADMIN) {
			throw new ResponseStatusException(HttpStatus.FORBIDDEN, "只有 OWNER 或 ADMIN 可以创建邀请");
		}
		byte[] entropy = new byte[32];
		SECURE_RANDOM.nextBytes(entropy);
		String code = Base64.getUrlEncoder().withoutPadding().encodeToString(entropy);
		Instant expiresAt = Instant.now().plus(INVITATION_TTL);
		invitationRepository.save(new WorkspaceInvitation(
				UUID.randomUUID().toString(), tenantId, sha256(code), actorId, expiresAt));
		return new WorkspaceDtos.InvitationResponse(code, tenantId, workspace.getName(), expiresAt);
	}

	@Transactional
	public WorkspaceDtos.WorkspaceSummary acceptInvitation(String userId, String rawCode) {
		requireUser(userId);
		String code = rawCode == null ? "" : rawCode.trim();
		WorkspaceInvitation invitation = invitationRepository.findByCodeHash(sha256(code))
				.orElseThrow(() -> new ResponseStatusException(HttpStatus.NOT_FOUND, "邀请码无效"));
		Instant now = Instant.now();
		if (invitation.isAccepted()) {
			throw new ResponseStatusException(HttpStatus.CONFLICT, "邀请码已被使用");
		}
		if (!invitation.getExpiresAt().isAfter(now)) {
			throw new ResponseStatusException(HttpStatus.GONE, "邀请码已过期");
		}
		if (memberRepository.findByTenantIdAndUserId(invitation.getTenantId(), userId).isPresent()) {
			throw new ResponseStatusException(HttpStatus.CONFLICT, "你已经是该工作区成员");
		}
		Workspace workspace = requireWorkspace(invitation.getTenantId());
		WorkspaceMember member = memberRepository.save(new WorkspaceMember(
				UUID.randomUUID().toString(), workspace.getTenantId(), userId,
				WorkspaceMember.WorkspaceRole.MEMBER));
		invitation.accept(userId, now);
		return summary(workspace, member);
	}

	@Transactional
	public WorkspaceDtos.MemberView updateMemberRole(
			String actorId, String tenantId, String targetUserId, WorkspaceMember.WorkspaceRole role) {
		WorkspaceMember actor = requireMembership(tenantId, actorId);
		if (actor.getRole() != WorkspaceMember.WorkspaceRole.OWNER) {
			throw new ResponseStatusException(HttpStatus.FORBIDDEN, "只有 OWNER 可以调整成员角色");
		}
		if (role == WorkspaceMember.WorkspaceRole.OWNER) {
			throw new ResponseStatusException(HttpStatus.BAD_REQUEST, "不能通过成员角色接口授予 OWNER");
		}
		WorkspaceMember target = requireMembership(tenantId, targetUserId);
		if (target.getRole() == WorkspaceMember.WorkspaceRole.OWNER) {
			throw new ResponseStatusException(HttpStatus.CONFLICT, "不能降级 Workspace OWNER");
		}
		target.setRole(role);
		UserAccount user = requireUser(targetUserId);
		return new WorkspaceDtos.MemberView(
				targetUserId, user.getUsername(), role, role.jwtRole(), target.getJoinedAt());
	}

	private WorkspaceMember requireMembership(String tenantId, String userId) {
		return memberRepository.findByTenantIdAndUserId(tenantId, userId)
				.orElseThrow(() -> new ResponseStatusException(HttpStatus.NOT_FOUND, "工作区不存在"));
	}

	private Workspace requireWorkspace(String tenantId) {
		return workspaceRepository.findById(tenantId)
				.orElseThrow(() -> new ResponseStatusException(HttpStatus.NOT_FOUND, "工作区不存在"));
	}

	private UserAccount requireUser(String userId) {
		return userRepository.findById(userId)
				.orElseThrow(() -> new ResponseStatusException(HttpStatus.NOT_FOUND, "用户不存在"));
	}

	private static WorkspaceDtos.WorkspaceSummary summary(Workspace workspace, WorkspaceMember member) {
		return new WorkspaceDtos.WorkspaceSummary(
				workspace.getTenantId(), workspace.getName(), workspace.getWorkspaceType().claimValue(),
				member.getRole(), member.getRole().jwtRole(), workspace.getCreatedBy(),
				workspace.getCreatedAt(), member.getJoinedAt());
	}

	private static String sha256(String value) {
		try {
			byte[] digest = MessageDigest.getInstance("SHA-256")
					.digest(value.getBytes(StandardCharsets.UTF_8));
			return java.util.HexFormat.of().formatHex(digest);
		} catch (NoSuchAlgorithmException impossible) {
			throw new IllegalStateException("SHA-256 is unavailable", impossible);
		}
	}
}
