package com.example.videoplatform.workflow;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;

import com.example.videoplatform.auth.UserAccount;
import com.example.videoplatform.auth.UserAccountRepository;
import java.util.UUID;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.test.mock.mockito.MockBean;

@SpringBootTest(properties = {
		"app.workflow.dispatcher-enabled=false",
		"spring.datasource.url=jdbc:h2:mem:workflow-dispatch-atomicity;DB_CLOSE_DELAY=-1;DB_CLOSE_ON_EXIT=FALSE"
})
class WorkflowDispatchAtomicityIntegrationTests {

	@Autowired VideoTaskService videoTaskService;
	@Autowired VideoTaskRepository taskRepository;
	@Autowired UserAccountRepository userAccountRepository;
	@MockBean WorkflowDispatchOutboxService workflowDispatchOutboxService;

	@Test
	void taskCreationRollsBackWhenDispatchIntentCannotBePersisted() {
		String owner = "atomic-" + UUID.randomUUID();
		userAccountRepository.saveAndFlush(new UserAccount(owner, owner, "hash"));
		org.mockito.Mockito.doThrow(new IllegalStateException("outbox unavailable"))
				.when(workflowDispatchOutboxService).enqueue(org.mockito.ArgumentMatchers.anyString());

		assertThatThrownBy(() -> videoTaskService.createTask(owner, "demo.mp4", "storage/demo.mp4"))
				.isInstanceOf(IllegalStateException.class)
				.hasMessageContaining("outbox unavailable");

		assertThat(taskRepository.findByOwnerOrderByCreatedAtDesc(owner)).isEmpty();
	}
}
