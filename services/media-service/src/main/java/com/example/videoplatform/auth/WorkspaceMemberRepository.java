package com.example.videoplatform.auth;

import java.util.Optional;
import org.springframework.data.jpa.repository.JpaRepository;

public interface WorkspaceMemberRepository extends JpaRepository<WorkspaceMember, String> {

	Optional<WorkspaceMember> findByTenantIdAndUserId(String tenantId, String userId);
}
