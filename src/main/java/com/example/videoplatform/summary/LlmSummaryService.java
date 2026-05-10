package com.example.videoplatform.summary;

import org.springframework.boot.autoconfigure.condition.ConditionalOnProperty;
import org.springframework.stereotype.Service;

@Service
@ConditionalOnProperty(prefix = "app.summary", name = "enabled", havingValue = "true")
public class LlmSummaryService implements SummaryService {

	private final OpenAiCompatibleSummaryClient summaryClient;

	public LlmSummaryService(OpenAiCompatibleSummaryClient summaryClient) {
		this.summaryClient = summaryClient;
	}

	@Override
	public String summarize(String transcript) {
		return summaryClient.summarize(transcript);
	}
}
