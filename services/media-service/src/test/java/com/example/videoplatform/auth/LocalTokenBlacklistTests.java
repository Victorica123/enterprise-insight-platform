package com.example.videoplatform.auth;

import static org.assertj.core.api.Assertions.assertThat;

import java.time.Instant;
import java.time.temporal.ChronoUnit;
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
}
