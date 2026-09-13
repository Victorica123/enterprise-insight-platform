package com.example.videoplatform.transcript;

import com.example.videoplatform.config.AppProperties;
import com.example.videoplatform.workflow.TaskStageLog.Stage;
import com.example.videoplatform.workflow.TaskStageObserver;
import java.nio.file.Files;
import java.nio.file.Path;
import org.springframework.boot.autoconfigure.condition.ConditionalOnProperty;
import org.springframework.stereotype.Service;

@Service
@ConditionalOnProperty(prefix = "app.transcript", name = "enabled", havingValue = "true")
public class WhisperTranscriptService implements TranscriptService {

	private final AppProperties appProperties;
	private final AudioExtractionService audioExtractionService;
	private final OpenAiCompatibleWhisperClient whisperClient;

	public WhisperTranscriptService(
			AppProperties appProperties,
			AudioExtractionService audioExtractionService,
			OpenAiCompatibleWhisperClient whisperClient) {
		this.appProperties = appProperties;
		this.audioExtractionService = audioExtractionService;
		this.whisperClient = whisperClient;
	}

	@Override
	public TranscriptResult extract(String storagePath, String fileName) {
		return extract(storagePath, fileName, TaskStageObserver.untracked());
	}

	@Override
	public TranscriptResult extract(String storagePath, String fileName, TaskStageObserver stages) {
		String ffmpegPath = appProperties.getTranscript().getWhisper().getFfmpegPath();
		Path wavPath = stages.run(Stage.AUDIO_EXTRACTION,
				() -> audioExtractionService.extractToWav(storagePath, ffmpegPath));
		try {
			return stages.run(Stage.TRANSCRIPTION, () -> whisperClient.transcribe(wavPath));
		} finally {
			try {
				Files.deleteIfExists(wavPath);
			} catch (Exception ignored) {
				// Best effort cleanup for temp audio file.
			}
		}
	}
}
