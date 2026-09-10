package com.example.videoplatform.auth;

import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.Id;
import jakarta.persistence.Table;
import jakarta.persistence.UniqueConstraint;

@Entity
@Table(name = "user_account", uniqueConstraints = {
		// existsByUsername 的 check-then-save 在并发注册下存在 TOCTOU 窗口，
		// 唯一约束是最终防线：重名插入抛 DataIntegrityViolationException → 全局处理为 409。
		@UniqueConstraint(name = "uk_user_account_username", columnNames = "username"),
		@UniqueConstraint(name = "uk_user_account_oidc_identity", columnNames = {"identityIssuer", "identitySubject"})
})
public class UserAccount {

	@Id
	private String userId;

	@Column(nullable = false, length = 50)
	private String username;

	private String passwordHash;

	@Column(length = 255)
	private String identityIssuer;

	@Column(length = 255)
	private String identitySubject;

	@Column(length = 64)
	private String primaryTenantId;

	protected UserAccount() {
		// JPA requires no-arg constructor
	}

	public UserAccount(String userId, String username, String passwordHash) {
		this.userId = userId;
		this.username = username;
		this.passwordHash = passwordHash;
	}

	public static UserAccount oidc(String userId, String username, String issuer, String subject) {
		UserAccount user = new UserAccount(userId, username, null);
		user.identityIssuer = issuer;
		user.identitySubject = subject;
		return user;
	}

	public String getUserId() {
		return userId;
	}

	public String getUsername() {
		return username;
	}

	public String getPasswordHash() {
		return passwordHash;
	}

	public String getIdentityIssuer() {
		return identityIssuer;
	}

	public String getIdentitySubject() {
		return identitySubject;
	}

	public String getPrimaryTenantId() {
		return primaryTenantId;
	}

	public void setPrimaryTenantId(String primaryTenantId) {
		this.primaryTenantId = primaryTenantId;
	}
}
