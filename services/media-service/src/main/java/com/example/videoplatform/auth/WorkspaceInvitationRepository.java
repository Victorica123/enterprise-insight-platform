package com.example.videoplatform.auth;

import jakarta.persistence.LockModeType;
import java.util.Optional;
import org.springframework.data.jpa.repository.JpaRepository;
import org.springframework.data.jpa.repository.Lock;

public interface WorkspaceInvitationRepository extends JpaRepository<WorkspaceInvitation, String> {

	@Lock(LockModeType.PESSIMISTIC_WRITE)
	Optional<WorkspaceInvitation> findByCodeHash(String codeHash);
}
