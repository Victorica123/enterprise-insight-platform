package com.example.videoplatform.auth;

import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.EnumType;
import jakarta.persistence.Enumerated;
import jakarta.persistence.Id;
import jakarta.persistence.Table;
import jakarta.persistence.UniqueConstraint;
import java.time.Instant;

@Entity
@Table(name = "workspace_member", uniqueConstraints = {
		@UniqueConstraint(name = "uk_workspace_member_tenant_user", columnNames = {"tenantId", "userId"})
})
public class WorkspaceMember {

	@Id
	private String memberId;

	@Column(nullable = false, length = 64)
	private String tenantId;

	@Column(nullable = false, length = 64)
	private String userId;

	@Enumerated(EnumType.STRING)
	@Column(nullable = false, length = 20)
	private WorkspaceRole role;

	@Column(nullable = false)
	private Instant joinedAt;

	protected WorkspaceMember() {
		// JPA
	}

	public WorkspaceMember(String memberId, String tenantId, String userId, WorkspaceRole role) {
		this.memberId = memberId;
		this.tenantId = tenantId;
		this.userId = userId;
		this.role = role;
		this.joinedAt = Instant.now();
	}

	public String getTenantId() {
		return tenantId;
	}

	public String getUserId() {
		return userId;
	}

	public WorkspaceRole getRole() {
		return role;
	}

	public Instant getJoinedAt() {
		return joinedAt;
	}

	public void setRole(WorkspaceRole role) {
		this.role = role;
	}

	public enum WorkspaceRole {
		OWNER("admin"),
		ADMIN("admin"),
		MEMBER("operator"),
		VIEWER("viewer");

		private final String jwtRole;

		WorkspaceRole(String jwtRole) {
			this.jwtRole = jwtRole;
		}

		public String jwtRole() {
			return jwtRole;
		}
	}
}
