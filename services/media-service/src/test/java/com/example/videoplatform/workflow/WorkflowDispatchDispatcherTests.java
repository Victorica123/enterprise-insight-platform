package com.example.videoplatform.workflow;

import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.when;

import java.lang.reflect.Field;
import java.time.Instant;
import java.util.List;
import org.junit.jupiter.api.Test;

class WorkflowDispatchDispatcherTests {

	private final WorkflowDispatchOutboxService outboxService =
			org.mockito.Mockito.mock(WorkflowDispatchOutboxService.class);
	private final WorkflowPublisher publisher = org.mockito.Mockito.mock(WorkflowPublisher.class);
	private final WorkflowDispatchDispatcher dispatcher = new WorkflowDispatchDispatcher(outboxService, publisher);

	@Test
	void marksAcceptedDispatchAsSent() throws Exception {
		WorkflowDispatchOutbox event = claimedEvent("task-1", "claim-1");
		when(outboxService.claimBatch()).thenReturn(List.of(event));
		when(outboxService.markSent("task-1", "claim-1")).thenReturn(true);

		dispatcher.dispatchPending();

		verify(publisher).publish("task-1");
		verify(outboxService).markSent("task-1", "claim-1");
	}

	@Test
	void persistsRetryWhenTransportRejectsDispatch() throws Exception {
		WorkflowDispatchOutbox event = claimedEvent("task-2", "claim-2");
		when(outboxService.claimBatch()).thenReturn(List.of(event));
		when(outboxService.markRetry("task-2", "claim-2", "executor saturated")).thenReturn(true);
		org.mockito.Mockito.doThrow(new IllegalStateException("executor saturated"))
				.when(publisher).publish("task-2");

		dispatcher.dispatchPending();

		verify(outboxService).markRetry("task-2", "claim-2", "executor saturated");
	}

	private static WorkflowDispatchOutbox claimedEvent(String taskId, String claimId) throws Exception {
		WorkflowDispatchOutbox event = new WorkflowDispatchOutbox(taskId);
		set(event, "status", WorkflowDispatchOutbox.DispatchStatus.CLAIMED);
		set(event, "claimId", claimId);
		set(event, "claimExpiresAt", Instant.now().plusSeconds(30));
		return event;
	}

	private static void set(Object target, String fieldName, Object value) throws Exception {
		Field field = target.getClass().getDeclaredField(fieldName);
		field.setAccessible(true);
		field.set(target, value);
	}
}
