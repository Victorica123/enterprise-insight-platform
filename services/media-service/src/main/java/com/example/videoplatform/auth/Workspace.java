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

	@Column(nullable = false)
	private Instant createdAt;

	protected Workspace() {
		// JPA
	}

	public Workspace(String tenantId, String name, String createdBy) {
		this.tenantId = tenantId;
		this.name = name;
		this.createdBy = createdBy;
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

	public Instant getCreatedAt() {
		return createdAt;
	}
}
