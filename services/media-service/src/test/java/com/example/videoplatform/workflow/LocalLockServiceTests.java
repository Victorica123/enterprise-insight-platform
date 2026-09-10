package com.example.videoplatform.workflow;

import static org.assertj.core.api.Assertions.assertThat;

import java.util.concurrent.CountDownLatch;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicBoolean;
import org.junit.jupiter.api.Test;

class LocalLockServiceTests {

	@Test
	void releasesEntriesForHighCardinalityKeys() {
		LocalLockService locks = new LocalLockService();
		for (int index = 0; index < 1_000; index++) {
			String key = "asset-" + index;
			assertThat(locks.tryLock(key, 30)).isTrue();
			locks.unlock(key);
		}
		assertThat(locks.lockEntryCount()).isZero();
	}

	@Test
	void failedContenderCannotRemoveOwnersLockEntry() throws Exception {
		LocalLockService locks = new LocalLockService();
		assertThat(locks.tryLock("shared", 30)).isTrue();
		CountDownLatch attempted = new CountDownLatch(1);
		AtomicBoolean acquired = new AtomicBoolean(true);
		Thread contender = new Thread(() -> {
			acquired.set(locks.tryLock("shared", 30));
			attempted.countDown();
		});
		contender.start();
		assertThat(attempted.await(2, TimeUnit.SECONDS)).isTrue();
		contender.join();

		assertThat(acquired).isFalse();
		assertThat(locks.lockEntryCount()).isEqualTo(1);
		locks.unlock("shared");
		assertThat(locks.lockEntryCount()).isZero();
	}
}
