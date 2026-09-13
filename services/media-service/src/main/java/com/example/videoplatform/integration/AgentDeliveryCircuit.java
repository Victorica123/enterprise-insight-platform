package com.example.videoplatform.integration;

import com.example.videoplatform.config.IntegrationProperties;
import java.time.Clock;
import java.time.Instant;

/** Process-local availability guard. Durable retries remain exclusively in the outbox. */
final class AgentDeliveryCircuit {
    private final IntegrationProperties.Agent properties;
    private final Clock clock;
    private int failures;
    private int openings;
    private long generation;
    private boolean probeInFlight;
    private Instant openUntil = Instant.EPOCH;

    AgentDeliveryCircuit(IntegrationProperties.Agent properties, Clock clock) {
        this.properties = properties;
        this.clock = clock;
    }

    synchronized boolean canAttempt() { return !probeInFlight && !clock.instant().isBefore(openUntil); }

    synchronized Permit acquire() {
        if (!canAttempt()) throw new OpenException(retryAt());
        boolean probe = failures >= Math.max(1, properties.getCircuitFailureThreshold());
        if (probe) probeInFlight = true;
        return new Permit(generation, probe);
    }

    synchronized void succeeded(Permit permit) {
        if (permit.generation() != generation) return;
        failures = 0;
        openings = 0;
        probeInFlight = false;
        openUntil = Instant.EPOCH;
        generation++;
    }

    synchronized void failed(Permit permit) {
        if (permit.generation() != generation) return;
        probeInFlight = false;
        if (++failures >= Math.max(1, properties.getCircuitFailureThreshold())) {
            long base = Math.max(1, properties.getCircuitOpenMs());
            long cap = Math.max(base, properties.getCircuitMaxOpenMs());
            long multiplier = 1L << Math.min(20, openings++);
            long duration = base > cap / multiplier ? cap : Math.min(cap, base * multiplier);
            openUntil = clock.instant().plusMillis(duration);
            generation++;
        }
    }

    private Instant retryAt() {
        return openUntil.isAfter(clock.instant()) ? openUntil : clock.instant().plusSeconds(1);
    }

    record Permit(long generation, boolean probe) { }

    static final class OpenException extends IllegalStateException {
        private final Instant retryAt;
        OpenException(Instant retryAt) {
            super("Agent ingestion circuit is open");
            this.retryAt = retryAt;
        }
        Instant retryAt() { return retryAt; }
    }
}
