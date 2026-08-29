package com.example.videoplatform.auth;

import static org.assertj.core.api.Assertions.assertThat;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.multipart;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import java.nio.charset.StandardCharsets;
import java.nio.file.Path;
import java.time.Duration;
import java.util.concurrent.atomic.AtomicReference;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.io.TempDir;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.http.MediaType;
import org.springframework.mock.web.MockMultipartFile;
import org.springframework.test.context.DynamicPropertyRegistry;
import org.springframework.test.context.DynamicPropertySource;
import org.springframework.test.web.servlet.MockMvc;
import org.springframework.test.web.servlet.MvcResult;

/**
 * 回归测试：用「真实注册接口签发的 JWT」走完整上传链路。
 *
 * <p>背景：controller 单测用 {@code .with(user("alice"))} 模拟认证时，principal 恰好等于测试种子的
 * userId，掩盖了真实 JWT 链路上 username/userId 语义不一致导致的「用户不存在」上传失败。
 * 本测试强制经过真实 {@code JwtAuthenticationFilter}，任何身份语义回归都会在此暴露。
 */
@SpringBootTest(properties = {
		"app.redis.enabled=false",
		"app.mq.enabled=false",
		"spring.docker.compose.enabled=false",
		// 显式开启配额：确保 assertCanCreateTask→lockOwner（findByUserId）真实路径被执行。
		// 该路径在 application-test.yml 中因 quota=0 被跳过，而它正是身份语义 bug 的藏身处。
		"app.quota.max-active-tasks-per-user=5",
		"spring.autoconfigure.exclude="
				+ "org.apache.rocketmq.spring.autoconfigure.RocketMQAutoConfiguration,"
				+ "org.springframework.boot.autoconfigure.data.redis.RedisAutoConfiguration,"
				+ "org.springframework.boot.autoconfigure.data.redis.RedisRepositoriesAutoConfiguration"
})
@AutoConfigureMockMvc
class RealJwtUploadFlowTests {

	private static final Duration COMPLETION_TIMEOUT = Duration.ofSeconds(10);

	@TempDir
	static Path storageDir;

	@DynamicPropertySource
	static void storageProps(DynamicPropertyRegistry registry) {
		registry.add("app.storage.base-path", () -> storageDir.toString());
	}

	@Autowired
	private MockMvc mockMvc;

	@Autowired
	private ObjectMapper objectMapper;

	@Test
	void registeredUserCanUploadAndCompleteThroughRealJwtFilter() throws Exception {
		// 1. 真实注册 → 拿 token 与 userId
		JsonNode auth = registerAndReturn("flow-user");
		String token = auth.path("token").asText();
		String userId = auth.path("userId").asText();
		String tenantId = auth.path("tenantId").asText();

		// 2. 真实 JWT 过 Bearer 上传（真实过滤器 + 真实存储 + 真实配额校验）
		MockMultipartFile file = new MockMultipartFile(
				"file", "demo.mp4", "video/mp4", "fake-video-content".getBytes(StandardCharsets.UTF_8));
		MvcResult uploadResult = mockMvc.perform(multipart("/api/media/upload/file")
						.file(file)
						.header("Authorization", "Bearer " + token))
				.andExpect(status().isOk())
				.andExpect(jsonPath("$.success").value(true))
				.andReturn();
		JsonNode upload = objectMapper.readTree(uploadResult.getResponse().getContentAsString())
				.path("data");
		String taskId = upload.path("taskId").asText();

		// 3. 轮询直到异步工作流完成（Mock 转写/摘要，秒级）
		AtomicReference<JsonNode> completed = new AtomicReference<>();
		awaitCompletion(token, taskId, completed);

		// 4. 关键断言：owner 必须是注册返回的 userId（身份语义回归即失败）
		assertThat(completed.get().path("owner").asText()).isEqualTo(userId);
		assertThat(completed.get().path("tenantId").asText()).isEqualTo(tenantId);
		assertThat(completed.get().path("status").asText()).isEqualTo("COMPLETED");
		assertThat(completed.get().path("transcript").asText()).isNotBlank();
	}

	@Test
	void playbackTokenMustNotAuthenticateApiRequests() throws Exception {
		// 令牌混用回归：带 purpose 的短时效令牌不得当作登录凭证
		JsonNode auth = registerAndReturn("purpose-user");
		String token = auth.path("token").asText();
		String userId = auth.path("userId").asText();

		// 先用正常令牌上传并等待完成，拿播放令牌
		MockMultipartFile file = new MockMultipartFile(
				"file", "demo.mp4", "video/mp4", "fake-video-content".getBytes(StandardCharsets.UTF_8));
		MvcResult uploadResult = mockMvc.perform(multipart("/api/media/upload/file")
						.file(file)
						.header("Authorization", "Bearer " + token))
				.andExpect(status().isOk())
				.andReturn();
		String taskId = objectMapper.readTree(uploadResult.getResponse().getContentAsString())
				.path("data").path("taskId").asText();
		AtomicReference<JsonNode> completed = new AtomicReference<>();
		awaitCompletion(token, taskId, completed);

		MvcResult playbackResult = mockMvc.perform(get("/api/media/video/" + taskId + "/playback-token")
						.header("Authorization", "Bearer " + token))
				.andExpect(status().isOk())
				.andReturn();
		String playbackToken = objectMapper.readTree(playbackResult.getResponse().getContentAsString())
				.path("data").path("token").asText();

		// 播放令牌作为 Bearer 访问受保护 API 必须被拒绝（上下文未认证 → 403）
		mockMvc.perform(get("/api/workflow/tasks")
						.header("Authorization", "Bearer " + playbackToken))
				.andExpect(status().isForbidden());
	}

	private JsonNode registerAndReturn(String usernamePrefix) throws Exception {
		String username = usernamePrefix + "-" + System.nanoTime();
		MvcResult result = mockMvc.perform(post("/api/auth/register")
						.contentType(MediaType.APPLICATION_JSON)
						.content("{\"username\":\"%s\",\"password\":\"secret123\"}".formatted(username)))
				.andExpect(status().isOk())
				.andExpect(jsonPath("$.data.token").isNotEmpty())
				.andReturn();
		return objectMapper.readTree(result.getResponse().getContentAsString()).path("data");
	}

	private void awaitCompletion(String token, String taskId, AtomicReference<JsonNode> completed)
			throws Exception {
		long deadline = System.nanoTime() + COMPLETION_TIMEOUT.toNanos();
		while (System.nanoTime() < deadline) {
			MvcResult result;
			try {
				result = mockMvc.perform(get("/api/workflow/tasks/" + taskId)
								.header("Authorization", "Bearer " + token))
						.andExpect(status().isOk())
						.andReturn();
			} catch (AssertionError | Exception retry) {
				Thread.sleep(200);
				continue;
			}
			JsonNode task = objectMapper.readTree(
					result.getResponse().getContentAsString(StandardCharsets.UTF_8)).path("data");
			if ("COMPLETED".equals(task.path("status").asText()) || "FAILED".equals(task.path("status").asText())) {
				completed.set(task);
				return;
			}
			Thread.sleep(200);
		}
		throw new AssertionError("任务在 " + COMPLETION_TIMEOUT + " 内未到达终态: " + taskId);
	}
}
