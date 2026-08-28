package com.example.videoplatform.auth;

import jakarta.persistence.LockModeType;
import org.springframework.data.jpa.repository.JpaRepository;
import org.springframework.data.jpa.repository.Lock;
import org.springframework.stereotype.Repository;

import java.util.Optional;

@Repository
public interface UserAccountRepository extends JpaRepository<UserAccount, String> {
	Optional<UserAccount> findByUsername(String username);
	boolean existsByUsername(String username);

	/**
	 * 创建任务前锁住用户行，避免同一用户的并发上传同时通过 active-task 配额检查。
	 */
	@Lock(LockModeType.PESSIMISTIC_WRITE)
	Optional<UserAccount> findByUserId(String userId);
}
