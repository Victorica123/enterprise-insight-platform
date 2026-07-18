package com.example.videoplatform.workflow;

import static org.assertj.core.api.Assertions.assertThat;

import com.example.videoplatform.auth.UserAccount;
import com.example.videoplatform.auth.UserAccountRepository;
import java.util.ArrayList;
import java.util.List;
import java.util.UUID;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.context.TestPropertySource;

@SpringBootTest
@TestPropertySource(properties = "app.quota.max-active-tasks-per-user=3")
class VideoTaskQuotaIntegrationTests {

	@Autowired
	private VideoTaskService videoTaskService;

	@Autowired
	private VideoTaskRepository taskRepository;

	@Autowired
	private UserAccountRepository userAccountRepository;

	@Test
	void concurrentCreatesCannotExceedOwnerLimit() throws Exception {
		String owner = "quota-owner-" + UUID.randomUUID();
		userAccountRepository.save(new UserAccount(owner, "quota-user-" + UUID.randomUUID(), "hash"));

		int requests = 10;
		ExecutorService executor = Executors.newFixedThreadPool(requests);
		CountDownLatch ready = new CountDownLatch(requests);
		CountDownLatch start = new CountDownLatch(1);
		List<Future<Boolean>> results = new ArrayList<>();
		try {
			for (int index = 0; index < requests; index++) {
				int requestIndex = index;
				results.add(executor.submit(() -> {
					ready.countDown();
					start.await();
					try {
						videoTaskService.createTask(owner, "quota-" + requestIndex + ".mp4",
								"storage/quota-" + requestIndex + ".mp4");
						return true;
					} catch (ActiveTaskLimitExceededException expected) {
						return false;
					}
				}));
			}

			ready.await();
			start.countDown();
			long accepted = 0;
			for (Future<Boolean> result : results) {
				if (result.get()) {
					accepted++;
				}
			}

			assertThat(accepted).isEqualTo(3);
			assertThat(taskRepository.countByOwnerAndStatusIn(owner, List.of(
					VideoTask.TaskStatus.QUEUED,
					VideoTask.TaskStatus.TRANSCRIBING,
					VideoTask.TaskStatus.SUMMARIZING))).isEqualTo(3);
		} finally {
			executor.shutdownNow();
		}
	}
}
