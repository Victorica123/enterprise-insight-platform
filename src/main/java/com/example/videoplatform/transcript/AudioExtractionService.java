package com.example.videoplatform.transcript;

import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.time.Instant;
import java.util.ArrayList;
import java.util.List;
import org.springframework.stereotype.Component;

@Component
public class AudioExtractionService {

	public Path extractToWav(String inputFilePath, String ffmpegPath) {
		Path input = Path.of(inputFilePath);
		if (!Files.exists(input)) {
			throw new IllegalArgumentException("视频文件不存在: " + inputFilePath);
		}

		Path tempDir = Path.of(System.getProperty("java.io.tmpdir"), "video-platform", "audio");
		try {
			Files.createDirectories(tempDir);
		} catch (IOException exception) {
			throw new IllegalStateException("无法创建临时目录: " + tempDir, exception);
		}

		String fileName = "audio-" + Instant.now().toEpochMilli() + ".wav";
		Path output = tempDir.resolve(fileName);

		List<String> command = new ArrayList<>();
		command.add(ffmpegPath);
		command.add("-y");
		command.add("-i");
		command.add(input.toString());
		command.add("-vn");
		command.add("-ac");
		command.add("1");
		command.add("-ar");
		command.add("16000");
		command.add("-f");
		command.add("wav");
		command.add(output.toString());

		ProcessBuilder processBuilder = new ProcessBuilder(command);
		processBuilder.redirectErrorStream(true);
		try {
			Process process = processBuilder.start();
			byte[] outputBytes = process.getInputStream().readAllBytes();
			int exitCode = process.waitFor();
			if (exitCode != 0 || !Files.exists(output)) {
				String message = new String(outputBytes, StandardCharsets.UTF_8);
				throw new IllegalStateException("FFmpeg 提取音频失败，exit=" + exitCode + "，日志: " + message);
			}
			return output;
		} catch (IOException exception) {
			throw new IllegalStateException("无法执行 FFmpeg，请检查 app.transcript.whisper.ffmpeg-path", exception);
		} catch (InterruptedException exception) {
			Thread.currentThread().interrupt();
			throw new IllegalStateException("FFmpeg 执行被中断", exception);
		}
	}
}
