package com.example.videoplatform.transcript;

import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.ArrayList;
import java.util.List;
import java.util.UUID;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicReference;
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

		// 使用 UUID 而非毫秒时间戳，避免同一毫秒内并发提取产生文件名冲突。
		String fileName = "audio-" + UUID.randomUUID() + ".mp3";
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
		command.add("-b:a");
		command.add("32k");
		command.add("-f");
		command.add("mp3");
		command.add(output.toString());

		ProcessBuilder processBuilder = new ProcessBuilder(command);
		processBuilder.redirectErrorStream(true);
		try {
			Process process = processBuilder.start();

			// 必须在等待进程结束的同时并发读取输出流：FFmpeg 输出较多时会写满 OS 管道缓冲区
			// （通常约 64KB）而阻塞，若仅在 waitFor 之后再读取，进程永远无法结束，会误判为超时。
			AtomicReference<byte[]> outputHolder = new AtomicReference<>(new byte[0]);
			Thread drainThread = new Thread(() -> {
				try {
					outputHolder.set(process.getInputStream().readAllBytes());
				} catch (IOException ignored) {
					// 进程被强制终止时读取会中断，忽略。
				}
			}, "ffmpeg-output-drain");
			drainThread.setDaemon(true);
			drainThread.start();

			boolean finished = process.waitFor(30, TimeUnit.SECONDS);
			if (!finished) {
				process.destroyForcibly();
				drainThread.interrupt();
				deleteQuietly(output);
				throw new IllegalStateException("FFmpeg 执行超时（30秒）");
			}
			drainThread.join(TimeUnit.SECONDS.toMillis(5));

			int exitCode = process.exitValue();
			if (exitCode != 0 || !Files.exists(output)) {
				String message = new String(outputHolder.get(), StandardCharsets.UTF_8);
				deleteQuietly(output);
				throw new IllegalStateException("FFmpeg 提取音频失败，exit=" + exitCode + "，日志: " + message);
			}
			return output;
		} catch (IOException exception) {
			deleteQuietly(output);
			throw new IllegalStateException("无法执行 FFmpeg，请检查 app.transcript.whisper.ffmpeg-path", exception);
		} catch (InterruptedException exception) {
			Thread.currentThread().interrupt();
			deleteQuietly(output);
			throw new IllegalStateException("FFmpeg 执行被中断", exception);
		}
	}

	private static void deleteQuietly(Path path) {
		try {
			Files.deleteIfExists(path);
		} catch (IOException ignored) {
			// Best effort cleanup.
		}
	}
}
