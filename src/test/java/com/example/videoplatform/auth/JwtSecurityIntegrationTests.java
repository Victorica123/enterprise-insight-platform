package com.example.videoplatform.auth;

import static org.hamcrest.Matchers.not;
import static org.hamcrest.Matchers.blankOrNullString;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
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

	private String registerAndReturnToken(String username) throws Exception {
		String response = mockMvc.perform(post("/api/auth/register")
						.contentType(MediaType.APPLICATION_JSON)
						.content("""
								{"username":"%s","password":"secret"}
								""".formatted(username)))
				.andExpect(status().isOk())
				.andExpect(jsonPath("$.data.token", not(blankOrNullString())))
				.andReturn()
				.getResponse()
				.getContentAsString();
		return objectMapper.readTree(response).path("data").path("token").asText();
	}
}
