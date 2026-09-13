package com.example.videoplatform.transcript;

import com.example.videoplatform.workflow.TaskStageLog.Stage;
import com.example.videoplatform.workflow.TaskStageObserver;

public interface TranscriptService {

	TranscriptResult extract(String storagePath, String fileName);

	default TranscriptResult extract(String storagePath, String fileName, TaskStageObserver stages) {
		return stages.run(Stage.TRANSCRIPTION, () -> extract(storagePath, fileName));
	}
}
