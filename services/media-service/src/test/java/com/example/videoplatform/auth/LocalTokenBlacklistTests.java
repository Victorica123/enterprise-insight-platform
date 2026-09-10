package com.example.videoplatform.auth;

import static org.assertj.core.api.Assertions.assertThat;

import java.time.Clock;
import java.time.Instant;
import java.time.ZoneId;
import java.time.temporal.ChronoUnit;
import java.util.concurrent.atomic.AtomicReference;
import org.junit.jupiter.api.Test;

class LocalTokenBlacklistTests {

	@Test
	void revokedTokenIsRejectedUntilExpiry() {
		LocalTokenBlacklist blacklist = new LocalTokenBlacklist();
		Instant expiry = Instant.now().plus(1, ChronoUnit.HOURS);

		blacklist.revoke("jti-1", expiry);

		assertThat(blacklist.isRevoked("jti-1")).isTrue();
		assertThat(blacklist.isRevoked("jti-2")).isFalse();
	}

	@Test
	void expiredEntryIsLazilyEvictedAndStopsBlocking() {
		LocalTokenBlacklist blacklist = new LocalTokenBlacklist();

		// 黑名单只应活到令牌自然过期：已过期条目不再拦截
		blacklist.revoke("jti-expired", Instant.now().minusSeconds(1));
		assertThat(blacklist.isRevoked("jti-expired")).isFalse();
	}

	@Test
	void alreadyExpiredTokenIsNotStored() {
		LocalTokenBlacklist blacklist = new LocalTokenBlacklist();

		blacklist.revoke("jti-1", Instant.now().minusSeconds(1));

		assertThat(blacklist.isRevoked("jti-1")).isFalse();
	}

	@Test
	void globallyEvictsExpiredTokensWithoutLookingUpEachJti() {
		MutableClock clock = new MutableClock(Instant.parse("2026-09-03T00:00:00Z"));
		LocalTokenBlacklist blacklist = new LocalTokenBlacklist(clock);
		for (int index = 0; index < 1_000; index++) {
			blacklist.revoke("jti-" + index, clock.instant().plusSeconds(30));
		}
		assertThat(blacklist.entryCount()).isEqualTo(1_000);

		clock.advanceSeconds(61);
		assertThat(blacklist.isRevoked("unrelated-jti")).isFalse();

		assertThat(blacklist.entryCount()).isZero();
	}

	private static final class MutableClock extends Clock {
		private final AtomicReference<Instant> now;

		private MutableClock(Instant initial) {
			this.now = new AtomicReference<>(initial);
		}

		void advanceSeconds(long seconds) {
			now.updateAndGet(value -> value.plusSeconds(seconds));
		}

		@Override
		public ZoneId getZone() {
			return ZoneId.of("UTC");
		}

		@Override
		public Clock withZone(ZoneId zone) {
			return this;
		}

		@Override
		public Instant instant() {
			return now.get();
		}
	}
}
