package com.example.videoplatform.transcript;

import com.example.videoplatform.common.StringUtils;
import com.example.videoplatform.config.AppProperties;
import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import java.io.IOException;
import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.time.Duration;
import java.util.UUID;
import org.springframework.stereotype.Component;

@Component
public class OpenAiCompatibleWhisperClient {

	private static final Duration CONNECT_TIMEOUT = Duration.ofSeconds(10);
	private static final Duration REQUEST_TIMEOUT = Duration.ofSeconds(90);

	private final AppProperties appProperties;
	private final HttpClient httpClient;
	private final ObjectMapper objectMapper;

	public OpenAiCompatibleWhisperClient(AppProperties appProperties, ObjectMapper objectMapper) {
		this.appProperties = appProperties;
		this.httpClient = HttpClient.newBuilder().connectTimeout(CONNECT_TIMEOUT).build();
		this.objectMapper = objectMapper;
	}

	public String transcribe(Path audioFile) {
		AppProperties.Transcript.Whisper whisper = appProperties.getTranscript().getWhisper();
		String baseUrl = whisper.getApiBaseUrl();
		String apiKey = whisper.getApiKey();
		if (StringUtils.isBlank(baseUrl) || StringUtils.isBlank(apiKey)) {
			throw new IllegalStateException("Whisper 配置缺失，请设置 app.transcript.whisper.api-base-url 和 api-key");
		}

		String boundary = "----Boundary" + UUID.randomUUID();
		String model = whisper.getModel();
		try {
			byte[] payload = buildMultipartPayload(audioFile, model, boundary);
			HttpRequest request = HttpRequest.newBuilder()
					.uri(URI.create(StringUtils.trimTrailingSlash(baseUrl) + "/audio/transcriptions"))
					.timeout(REQUEST_TIMEOUT)
					.header("Authorization", "Bearer " + apiKey)
					.header("Content-Type", "multipart/form-data; boundary=" + boundary)
					.POST(HttpRequest.BodyPublishers.ofByteArray(payload))
					.build();

			HttpResponse<String> response = httpClient.send(request, HttpResponse.BodyHandlers.ofString(StandardCharsets.UTF_8));
			if (response.statusCode() / 100 != 2) {
				throw new IllegalStateException("Whisper API 调用失败，status=" + response.statusCode() + "，body=" + response.body());
			}

			String text = extractJsonTextField(response.body());
			if (text == null) {
				throw new IllegalStateException("Whisper 返回缺少 text 字段: " + response.body());
			}
			return text;
		} catch (IOException exception) {
			throw new IllegalStateException("读取音频文件失败: " + audioFile, exception);
		} catch (InterruptedException exception) {
			Thread.currentThread().interrupt();
			throw new IllegalStateException("Whisper 请求被中断", exception);
		}
	}

	private static byte[] buildMultipartPayload(Path audioFile, String model, String boundary) throws IOException {
		String fileName = audioFile.getFileName().toString();
		String contentType = fileName.endsWith(".mp3") ? "audio/mpeg" : "audio/wav";
		StringBuilder head = new StringBuilder();
		head.append("--").append(boundary).append("\r\n");
		head.append("Content-Disposition: form-data; name=\"model\"\r\n\r\n");
		head.append(model).append("\r\n");
		head.append("--").append(boundary).append("\r\n");
		head.append("Content-Disposition: form-data; name=\"file\"; filename=\"").append(fileName).append("\"\r\n");
		head.append("Content-Type: ").append(contentType).append("\r\n\r\n");

		byte[] fileBytes = Files.readAllBytes(audioFile);
		byte[] headBytes = head.toString().getBytes(StandardCharsets.UTF_8);
		byte[] tailBytes = ("\r\n--" + boundary + "--\r\n").getBytes(StandardCharsets.UTF_8);

		byte[] payload = new byte[headBytes.length + fileBytes.length + tailBytes.length];
		System.arraycopy(headBytes, 0, payload, 0, headBytes.length);
		System.arraycopy(fileBytes, 0, payload, headBytes.length, fileBytes.length);
		System.arraycopy(tailBytes, 0, payload, headBytes.length + fileBytes.length, tailBytes.length);
		return payload;
	}

	private String extractJsonTextField(String body) {
		try {
			JsonNode root = objectMapper.readTree(body);
			JsonNode textNode = root.path("text");
			return textNode.isMissingNode() ? null : textNode.asText();
		} catch (IOException exception) {
			throw new IllegalStateException("Whisper 响应解析失败: " + body, exception);
		}
	}
}
