package com.example.videoplatform.auth;

import jakarta.persistence.Entity;
import jakarta.persistence.Id;
import jakarta.persistence.Table;

@Entity
@Table(name = "user_account")
public class UserAccount {

	@Id
	private String userId;

	private String username;

	private String passwordHash;

	protected UserAccount() {
		// JPA requires no-arg constructor
	}

	public UserAccount(String userId, String username, String passwordHash) {
		this.userId = userId;
		this.username = username;
		this.passwordHash = passwordHash;
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
}
