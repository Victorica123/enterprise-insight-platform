package com.example.videoplatform.auth;

import java.util.Optional;
import java.util.List;
import org.springframework.data.jpa.repository.JpaRepository;

public interface WorkspaceMemberRepository extends JpaRepository<WorkspaceMember, String> {

	Optional<WorkspaceMember> findByTenantIdAndUserId(String tenantId, String userId);

	List<WorkspaceMember> findAllByUserIdOrderByJoinedAtAsc(String userId);

	List<WorkspaceMember> findAllByTenantIdOrderByJoinedAtAsc(String tenantId);
}
