package com.example.videoplatform.auth;

import static org.hamcrest.Matchers.not;
import static org.hamcrest.Matchers.blankOrNullString;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.header;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

import com.fasterxml.jackson.databind.ObjectMapper;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.http.MediaType;
import org.springframework.test.web.servlet.MockMvc;

@SpringBootTest(properties = {
		"app.redis.enabled=false",
		"app.mq.enabled=false",
		"spring.docker.compose.enabled=false",
		"spring.autoconfigure.exclude="
				+ "org.apache.rocketmq.spring.autoconfigure.RocketMQAutoConfiguration,"
				+ "org.springframework.boot.autoconfigure.data.redis.RedisAutoConfiguration,"
				+ "org.springframework.boot.autoconfigure.data.redis.RedisRepositoriesAutoConfiguration"
})
@AutoConfigureMockMvc
class JwtSecurityIntegrationTests {

	@Autowired
	private MockMvc mockMvc;

	@Autowired
	private ObjectMapper objectMapper;

	@Test
	void bearerTokenAuthenticatesProtectedWorkflowRequest() throws Exception {
		String token = registerAndReturnToken("alice");

		mockMvc.perform(get("/api/workflow/tasks")
						.header("Authorization", "Bearer " + token))
				.andExpect(status().isOk())
				.andExpect(jsonPath("$.success").value(true));
	}

	@Test
	void missingBearerTokenCannotAccessProtectedWorkflowRequest() throws Exception {
		mockMvc.perform(get("/api/workflow/tasks"))
				.andExpect(status().isForbidden());
	}

	@Test
	void registerRejectsShortPasswordWithBadRequest() throws Exception {
		mockMvc.perform(post("/api/auth/register")
						.contentType(MediaType.APPLICATION_JSON)
						.content("{\"username\":\"mallory\",\"password\":\"short\"}"))
				.andExpect(status().isBadRequest());
	}

	@Test
	void logoutBlacklistsTokenUntilExpiry() throws Exception {
		// JWT 无状态不可撤回：登出 = 服务端 jti 黑名单 + 客户端丢弃令牌
		String token = registerAndReturnToken("logout-user");

		mockMvc.perform(get("/api/workflow/tasks")
						.header("Authorization", "Bearer " + token))
				.andExpect(status().isOk());

		mockMvc.perform(post("/api/auth/logout")
						.header("Authorization", "Bearer " + token))
				.andExpect(status().isOk());

		// 同一令牌在过期前被黑名单拒绝（上下文未认证 → 403）
		mockMvc.perform(get("/api/workflow/tasks")
						.header("Authorization", "Bearer " + token))
				.andExpect(status().isForbidden());
	}

	@Test
	void excessiveFailedLoginsAreRateLimited() throws Exception {
		// 测试上下文 Redis 关闭 → LocalLoginRateLimiter（默认 5 次/300 秒滑动窗口）
		String username = "bruteforce-" + System.nanoTime();
		String body = "{\"username\":\"%s\",\"password\":\"wrong-password\"}".formatted(username);

		for (int attempt = 1; attempt <= 5; attempt += 1) {
			mockMvc.perform(post("/api/auth/login")
							.contentType(MediaType.APPLICATION_JSON)
							.content(body))
					.andExpect(status().isBadRequest()); // 用户名或密码错误
		}

		// 第 6 次触发滑动窗口上限 → 429 + Retry-After，且不再做密码比对
		mockMvc.perform(post("/api/auth/login")
						.contentType(MediaType.APPLICATION_JSON)
						.content(body))
				.andExpect(status().isTooManyRequests())
				.andExpect(header().string("Retry-After", "300"));
	}

	@Test
	void traceIdIsEchoedInResponseHeader() throws Exception {
		mockMvc.perform(get("/actuator/health").header("X-Trace-Id", "trace-abc12345"))
				.andExpect(status().isOk())
				.andExpect(header().string("X-Trace-Id", "trace-abc12345"));

		// 未携带时自动生成，保证每个响应都可追溯
		mockMvc.perform(get("/actuator/health"))
				.andExpect(header().exists("X-Trace-Id"));
	}

	private String registerAndReturnToken(String username) throws Exception {
		String response = mockMvc.perform(post("/api/auth/register")
						.contentType(MediaType.APPLICATION_JSON)
						.content("""
								{"username":"%s","password":"secret123"}
								""".formatted(username)))
				.andExpect(status().isOk())
				.andExpect(jsonPath("$.data.token", not(blankOrNullString())))
				.andReturn()
				.getResponse()
				.getContentAsString();
		return objectMapper.readTree(response).path("data").path("token").asText();
	}
}
