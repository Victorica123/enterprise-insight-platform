package com.example.videoplatform.integration;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;

import com.example.videoplatform.config.IntegrationProperties;
import java.time.Clock;
import java.time.Instant;
import java.time.ZoneId;
import org.junit.jupiter.api.Test;

class AgentDeliveryCircuitTests {
    private final MutableClock clock = new MutableClock();
    private final IntegrationProperties.Agent properties = new IntegrationProperties.Agent();
    private final AgentDeliveryCircuit circuit = new AgentDeliveryCircuit(properties, clock);

    @Test
    void opensAfterThresholdAndAllowsOnlyOneHalfOpenProbe() {
        for (int i = 0; i < 3; i++) circuit.failed(circuit.acquire());
        assertThat(circuit.canAttempt()).isFalse();
        assertThatThrownBy(circuit::acquire).isInstanceOf(AgentDeliveryCircuit.OpenException.class);
        clock.advance(30_000);
        var probe = circuit.acquire();
        assertThat(probe.probe()).isTrue();
        assertThatThrownBy(circuit::acquire).isInstanceOf(AgentDeliveryCircuit.OpenException.class);
        circuit.succeeded(probe);
        assertThat(circuit.canAttempt()).isTrue();
        assertThat(circuit.acquire().probe()).isFalse();
    }

    @Test
    void failedProbeBacksOffAndStaleSuccessCannotCloseAnOpenCircuit() {
        var stale = circuit.acquire();
        for (int i = 0; i < 3; i++) circuit.failed(circuit.acquire());
        circuit.succeeded(stale);
        assertThat(circuit.canAttempt()).isFalse();
        clock.advance(30_000);
        circuit.failed(circuit.acquire());
        clock.advance(30_000);
        assertThat(circuit.canAttempt()).isFalse();
        clock.advance(30_000);
        assertThat(circuit.canAttempt()).isTrue();
    }

    @Test
    void healthyResponseResetsConsecutiveFailureCount() {
        circuit.failed(circuit.acquire());
        circuit.failed(circuit.acquire());
        circuit.succeeded(circuit.acquire());
        circuit.failed(circuit.acquire());
        circuit.failed(circuit.acquire());
        assertThat(circuit.canAttempt()).isTrue();
    }

    static class MutableClock extends Clock {
        private Instant now = Instant.parse("2026-09-13T00:00:00Z");
        void advance(long millis) { now = now.plusMillis(millis); }
        @Override public ZoneId getZone() { return ZoneId.of("UTC"); }
        @Override public Clock withZone(ZoneId zone) { return this; }
        @Override public Instant instant() { return now; }
    }
}
