package com.example.videoplatform.summary;

import com.example.videoplatform.common.StringUtils;
import org.springframework.boot.autoconfigure.condition.ConditionalOnProperty;
import org.springframework.stereotype.Service;

@Service
@ConditionalOnProperty(prefix = "app.summary", name = "enabled", havingValue = "false", matchIfMissing = true)
public class MockSummaryService implements SummaryService {

	@Override
	public String summarize(String transcript) {
		if (StringUtils.isBlank(transcript)) {
			return "AI summary: no speech content was detected in this video.";
		}
		String shortText = transcript.length() > 100 ? transcript.substring(0, 100) + "..." : transcript;
		return "AI summary: video content has been processed. Key information: " + shortText;
	}
}
