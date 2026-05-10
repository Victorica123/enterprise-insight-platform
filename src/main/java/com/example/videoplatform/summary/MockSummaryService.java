package com.example.videoplatform.summary;

import org.springframework.boot.autoconfigure.condition.ConditionalOnProperty;
import org.springframework.stereotype.Service;

@Service
@ConditionalOnProperty(prefix = "app.summary", name = "enabled", havingValue = "false", matchIfMissing = true)
public class MockSummaryService implements SummaryService {

	@Override
	public String summarize(String transcript) {
		String shortText = transcript.length() > 100 ? transcript.substring(0, 100) + "..." : transcript;
		return "AI 总结: 视频内容已处理完成，核心信息如下: " + shortText;
	}
}
