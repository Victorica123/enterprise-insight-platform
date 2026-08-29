package com.example.videoplatform.auth;

import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.Id;
import jakarta.persistence.Table;
import jakarta.persistence.UniqueConstraint;
import java.time.Instant;

@Entity
@Table(name = "workspace_invitation", uniqueConstraints = {
		@UniqueConstraint(name = "uk_workspace_invitation_code_hash", columnNames = "codeHash")
})
public class WorkspaceInvitation {

	@Id
	private String invitationId;

	@Column(nullable = false, length = 64)
	private String tenantId;

	@Column(nullable = false, length = 64)
	private String codeHash;

	@Column(nullable = false, length = 64)
	private String createdBy;

	@Column(nullable = false)
	private Instant createdAt;

	@Column(nullable = false)
	private Instant expiresAt;

	@Column(length = 64)
	private String acceptedBy;

	private Instant acceptedAt;

	protected WorkspaceInvitation() {
		// JPA
	}

	public WorkspaceInvitation(String invitationId, String tenantId, String codeHash,
			String createdBy, Instant expiresAt) {
		this.invitationId = invitationId;
		this.tenantId = tenantId;
		this.codeHash = codeHash;
		this.createdBy = createdBy;
		this.createdAt = Instant.now();
		this.expiresAt = expiresAt;
	}

	public String getTenantId() { return tenantId; }
	public Instant getExpiresAt() { return expiresAt; }
	public boolean isAccepted() { return acceptedAt != null; }

	public void accept(String userId, Instant now) {
		this.acceptedBy = userId;
		this.acceptedAt = now;
	}
}
