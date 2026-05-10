package com.example.videoplatform.workflow;

import com.example.videoplatform.summary.SummaryService;
import com.example.videoplatform.transcript.TranscriptService;
import org.springframework.scheduling.annotation.Async;
import org.springframework.stereotype.Component;

@Component
public class WorkflowProcessor {

	private final VideoTaskService videoTaskService;
	private final TranscriptService transcriptService;
	private final SummaryService summaryService;

	public WorkflowProcessor(VideoTaskService videoTaskService, TranscriptService transcriptService,
			SummaryService summaryService) {
		this.videoTaskService = videoTaskService;
		this.transcriptService = transcriptService;
		this.summaryService = summaryService;
	}

	@Async
	public void processAsync(String taskId) {
		process(taskId);
	}

	public void process(String taskId) {
		VideoTask task = videoTaskService.requireTask(taskId);
		try {
			task.setStatus(VideoTask.TaskStatus.TRANSCRIBING);
			String transcript = transcriptService.extract(task.getStoragePath(), task.getFileName());
			task.setTranscript(transcript);
			task.setStatus(VideoTask.TaskStatus.SUMMARIZING);
			task.setSummary(summaryService.summarize(transcript));
			task.setStatus(VideoTask.TaskStatus.COMPLETED);
		} catch (Exception exception) {
			task.setStatus(VideoTask.TaskStatus.FAILED);
			task.setErrorMessage(exception.getMessage());
		}
	}
}
