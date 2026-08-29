package com.example.videoplatform.auth;

import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.Id;
import jakarta.persistence.Table;
import java.time.Instant;

@Entity
@Table(name = "workspace")
public class Workspace {

	@Id
	private String tenantId;

	@Column(nullable = false, length = 100)
	private String name;

	@Column(nullable = false, length = 64)
	private String createdBy;

	@jakarta.persistence.Enumerated(jakarta.persistence.EnumType.STRING)
	@Column(length = 20)
	private WorkspaceType workspaceType;

	@Column(nullable = false)
	private Instant createdAt;

	protected Workspace() {
		// JPA
	}

	public Workspace(String tenantId, String name, String createdBy) {
		this(tenantId, name, createdBy, WorkspaceType.PERSONAL);
	}

	public Workspace(String tenantId, String name, String createdBy, WorkspaceType workspaceType) {
		this.tenantId = tenantId;
		this.name = name;
		this.createdBy = createdBy;
		this.workspaceType = workspaceType;
		this.createdAt = Instant.now();
	}

	public String getTenantId() {
		return tenantId;
	}

	public String getName() {
		return name;
	}

	public String getCreatedBy() {
		return createdBy;
	}

	public WorkspaceType getWorkspaceType() {
		return workspaceType == null ? WorkspaceType.PERSONAL : workspaceType;
	}

	public Instant getCreatedAt() {
		return createdAt;
	}

	public enum WorkspaceType {
		PERSONAL("personal"),
		TEAM("team");

		private final String claimValue;

		WorkspaceType(String claimValue) {
			this.claimValue = claimValue;
		}

		public String claimValue() {
			return claimValue;
		}
	}
}
