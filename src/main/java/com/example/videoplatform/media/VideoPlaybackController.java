package com.example.videoplatform.media;

import com.example.videoplatform.auth.JwtService;
import com.example.videoplatform.common.ApiResponse;
import com.example.videoplatform.workflow.VideoTask;
import com.example.videoplatform.workflow.VideoTaskService;
import io.jsonwebtoken.Claims;
import jakarta.servlet.http.HttpServletResponse;
import java.io.IOException;
import java.io.InputStream;
import java.io.OutputStream;
import java.nio.file.Files;
import java.nio.file.Path;
import org.springframework.http.HttpHeaders;
import org.springframework.http.HttpStatus;
import org.springframework.security.core.Authentication;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RequestHeader;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.server.ResponseStatusException;

/**
 * 视频播放：像真实视频平台一样支持 HTTP Range 分段请求（拖动进度条、边下边播）。
 *
 * <p>{@code <video>} 标签发起的请求无法携带 Authorization 头，因此播放地址改用
 * 短时效签名令牌（{@link JwtService#generatePlaybackToken}）作为查询参数鉴权，
 * 令牌绑定 taskId + owner。此设计与后续对象存储的预签名 URL 一致，便于平滑迁移。
 */
@RestController
@RequestMapping("/api/media/video")
public class VideoPlaybackController {

	/** 单次响应最大分段，避免无 Range 的客户端一次性拉走整段大文件占满连接。 */
	private static final long MAX_CHUNK = 4L * 1024 * 1024;

	private final VideoTaskService videoTaskService;
	private final JwtService jwtService;

	public VideoPlaybackController(VideoTaskService videoTaskService, JwtService jwtService) {
		this.videoTaskService = videoTaskService;
		this.jwtService = jwtService;
	}

	/** 颁发播放令牌（需登录，且只能为自己的任务申请）。 */
	@GetMapping("/{taskId}/playback-token")
	public ApiResponse<MediaDtos.PlaybackTokenResponse> playbackToken(Authentication authentication,
			@PathVariable String taskId) {
		String owner = authentication.getName();
		VideoTask task = videoTaskService.requireTask(taskId, owner); // owner 校验，越权直接抛出
		String token = jwtService.generatePlaybackToken(task.getTaskId(), owner);
		String streamUrl = "/api/media/video/" + task.getTaskId() + "/stream?token=" + token;
		return ApiResponse.ok(new MediaDtos.PlaybackTokenResponse(token, streamUrl,
				jwtService.getPlaybackTokenSeconds()));
	}

	/** 分段流式播放。令牌自校验，无需登录头，故此路径在 SecurityConfig 放行。 */
	@GetMapping("/{taskId}/stream")
	public void stream(@PathVariable String taskId, @RequestParam String token,
			@RequestHeader(value = HttpHeaders.RANGE, required = false) String rangeHeader,
			HttpServletResponse response) throws IOException {
		String owner = verifyPlaybackToken(token, taskId);
		VideoTask task = videoTaskService.requireTask(taskId, owner);

		Path file = Path.of(task.getStoragePath());
		if (!Files.exists(file) || !Files.isRegularFile(file)) {
			throw new ResponseStatusException(HttpStatus.NOT_FOUND, "视频文件不存在");
		}
		long fileLength = Files.size(file);
		String contentType = probeContentType(file);

		long start = 0;
		long end = fileLength - 1;
		boolean partial = rangeHeader != null && rangeHeader.startsWith("bytes=");
		if (partial) {
			long[] range = parseRange(rangeHeader, fileLength);
			if (range == null) {
				response.setHeader(HttpHeaders.CONTENT_RANGE, "bytes */" + fileLength);
				response.sendError(HttpStatus.REQUESTED_RANGE_NOT_SATISFIABLE.value());
				return;
			}
			start = range[0];
			end = range[1];
		}

		// 单次响应封顶，客户端按 Range 续拉后续分段。
		if (end - start + 1 > MAX_CHUNK) {
			end = start + MAX_CHUNK - 1;
			partial = true; // 强制以 206 返回，告知客户端这是部分内容
		}
		long contentLength = end - start + 1;

		response.setHeader(HttpHeaders.ACCEPT_RANGES, "bytes");
		response.setContentType(contentType);
		response.setHeader(HttpHeaders.CONTENT_LENGTH, String.valueOf(contentLength));
		if (partial) {
			response.setStatus(HttpStatus.PARTIAL_CONTENT.value());
			response.setHeader(HttpHeaders.CONTENT_RANGE, "bytes " + start + "-" + end + "/" + fileLength);
		} else {
			response.setStatus(HttpStatus.OK.value());
		}

		writeRange(file, start, contentLength, response.getOutputStream());
	}

	private String verifyPlaybackToken(String token, String taskId) {
		try {
			Claims claims = jwtService.parse(token);
			if (!"playback".equals(claims.get("purpose")) || !taskId.equals(claims.get("taskId"))) {
				throw new ResponseStatusException(HttpStatus.FORBIDDEN, "播放令牌无效");
			}
			return claims.getSubject();
		} catch (ResponseStatusException e) {
			throw e;
		} catch (Exception e) {
			throw new ResponseStatusException(HttpStatus.UNAUTHORIZED, "播放令牌无效或已过期");
		}
	}

	/** 解析 Range 头，支持 {@code bytes=start-end}、{@code bytes=start-}、{@code bytes=-suffix}。越界返回 null。 */
	private static long[] parseRange(String rangeHeader, long fileLength) {
		String spec = rangeHeader.substring("bytes=".length()).trim();
		int dash = spec.indexOf('-');
		if (dash < 0) {
			return null;
		}
		String startStr = spec.substring(0, dash).trim();
		String endStr = spec.substring(dash + 1).trim();
		try {
			long start;
			long end;
			if (startStr.isEmpty()) {
				// bytes=-N：最后 N 字节
				long suffix = Long.parseLong(endStr);
				if (suffix <= 0) {
					return null;
				}
				start = Math.max(0, fileLength - suffix);
				end = fileLength - 1;
			} else {
				start = Long.parseLong(startStr);
				end = endStr.isEmpty() ? fileLength - 1 : Long.parseLong(endStr);
			}
			if (start > end || start >= fileLength) {
				return null;
			}
			end = Math.min(end, fileLength - 1);
			return new long[] { start, end };
		} catch (NumberFormatException e) {
			return null;
		}
	}

	private static void writeRange(Path file, long start, long length, OutputStream out) throws IOException {
		try (InputStream in = Files.newInputStream(file)) {
			long skipped = 0;
			while (skipped < start) {
				long s = in.skip(start - skipped);
				if (s <= 0) {
					break;
				}
				skipped += s;
			}
			byte[] buffer = new byte[8192];
			long remaining = length;
			while (remaining > 0) {
				int toRead = (int) Math.min(buffer.length, remaining);
				int read = in.read(buffer, 0, toRead);
				if (read == -1) {
					break;
				}
				out.write(buffer, 0, read);
				remaining -= read;
			}
			out.flush();
		}
	}

	private static String probeContentType(Path file) {
		try {
			String probed = Files.probeContentType(file);
			if (probed != null) {
				return probed;
			}
		} catch (IOException ignored) {
			// fall through to extension-based guess
		}
		String name = file.getFileName().toString().toLowerCase();
		if (name.endsWith(".mp4") || name.endsWith(".m4v")) {
			return "video/mp4";
		}
		if (name.endsWith(".webm")) {
			return "video/webm";
		}
		if (name.endsWith(".mov")) {
			return "video/quicktime";
		}
		if (name.endsWith(".mkv")) {
			return "video/x-matroska";
		}
		return "application/octet-stream";
	}
}
