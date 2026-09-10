package com.example.videoplatform.auth;

import static org.assertj.core.api.Assertions.assertThat;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.multipart;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.patch;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import java.util.Map;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.http.MediaType;
import org.springframework.mock.web.MockMultipartFile;
import org.springframework.test.web.servlet.MockMvc;

@SpringBootTest(properties = {
		"app.redis.enabled=false",
		"app.mq.enabled=false",
		"app.workflow.dispatcher-enabled=true",
		"spring.datasource.url=jdbc:h2:mem:workspace-collaboration;DB_CLOSE_DELAY=-1;DB_CLOSE_ON_EXIT=FALSE",
		"spring.docker.compose.enabled=false",
		"spring.autoconfigure.exclude="
				+ "org.apache.rocketmq.spring.autoconfigure.RocketMQAutoConfiguration,"
				+ "org.springframework.boot.autoconfigure.data.redis.RedisAutoConfiguration,"
				+ "org.springframework.boot.autoconfigure.data.redis.RedisRepositoriesAutoConfiguration"
})
@AutoConfigureMockMvc
class WorkspaceCollaborationIntegrationTests {

	private static final byte[] MINIMAL_MP4 = {
			0, 0, 0, 24, 'f', 't', 'y', 'p', 'i', 's', 'o', 'm', 0, 0, 2, 0
	};

	@Autowired private MockMvc mockMvc;
	@Autowired private ObjectMapper objectMapper;
	@Autowired private JwtService jwtService;

	@Test
	void ownerInvitesMemberAndSwitchReissuesTrustedWorkspaceClaims() throws Exception {
		JsonNode owner = register("team-owner");
		JsonNode team = json(post("/api/workspaces")
				.header("Authorization", bearer(owner))
				.contentType(MediaType.APPLICATION_JSON)
				.content("{\"name\":\"客户洞察团队\"}"), 200).path("data");
		String tenantId = team.path("tenantId").asText();
		assertThat(team.path("workspaceType").asText()).isEqualTo("team");
		assertThat(team.path("role").asText()).isEqualTo("OWNER");

		JsonNode invitation = json(post("/api/workspaces/" + tenantId + "/invitations")
				.header("Authorization", bearer(owner)), 200).path("data");
		String invitationCode = invitation.path("invitationCode").asText();
		assertThat(invitationCode).hasSizeGreaterThanOrEqualTo(32);

		JsonNode member = register("team-member");
		json(post("/api/workspaces/invitations/accept")
				.header("Authorization", bearer(member))
				.contentType(MediaType.APPLICATION_JSON)
				.content(objectMapper.writeValueAsString(Map.of("invitationCode", invitationCode))), 200);

		JsonNode switched = json(post("/api/workspaces/" + tenantId + "/switch")
				.header("Authorization", bearer(member)), 200).path("data");
		var claims = jwtService.parse(switched.path("token").asText());
		assertThat(switched.path("role").asText()).isEqualTo("operator");
		assertThat(switched.path("workspaceType").asText()).isEqualTo("team");
		assertThat(claims.get("tenant_id", String.class)).isEqualTo(tenantId);
		assertThat(claims.get("role", String.class)).isEqualTo("operator");
		assertThat(claims.get("workspace_type", String.class)).isEqualTo("team");

		mockMvc.perform(get("/api/workspaces")
					.header("Authorization", "Bearer " + switched.path("token").asText()))
				.andExpect(status().isOk())
				.andExpect(jsonPath("$.data[?(@.tenantId == '%s')].role".formatted(tenantId)).value("MEMBER"));

		JsonNode outsider = register("team-outsider");
		mockMvc.perform(post("/api/workspaces/invitations/accept")
					.header("Authorization", bearer(outsider))
					.contentType(MediaType.APPLICATION_JSON)
					.content(objectMapper.writeValueAsString(Map.of("invitationCode", invitationCode))))
				.andExpect(status().isConflict());
	}

	@Test
	void onlyOwnerCanChangeNonOwnerRoleAndViewerReceivesReadOnlyJwt() throws Exception {
		JsonNode owner = register("role-owner");
		String tenantId = json(post("/api/workspaces")
				.header("Authorization", bearer(owner))
				.contentType(MediaType.APPLICATION_JSON)
				.content("{\"name\":\"角色测试团队\"}"), 200)
				.path("data").path("tenantId").asText();
		String code = json(post("/api/workspaces/" + tenantId + "/invitations")
				.header("Authorization", bearer(owner)), 200)
				.path("data").path("invitationCode").asText();
		JsonNode member = register("role-member");
		String memberId = member.path("userId").asText();
		json(post("/api/workspaces/invitations/accept")
				.header("Authorization", bearer(member))
				.contentType(MediaType.APPLICATION_JSON)
				.content(objectMapper.writeValueAsString(Map.of("invitationCode", code))), 200);

		String memberTeamToken = json(post("/api/workspaces/" + tenantId + "/switch")
				.header("Authorization", bearer(member)), 200).path("data").path("token").asText();
		mockMvc.perform(patch("/api/workspaces/" + tenantId + "/members/" + owner.path("userId").asText())
					.header("Authorization", "Bearer " + memberTeamToken)
					.contentType(MediaType.APPLICATION_JSON)
					.content("{\"role\":\"VIEWER\"}"))
				.andExpect(status().isForbidden());

		mockMvc.perform(patch("/api/workspaces/" + tenantId + "/members/" + memberId)
					.header("Authorization", bearer(owner))
					.contentType(MediaType.APPLICATION_JSON)
					.content("{\"role\":\"VIEWER\"}"))
				.andExpect(status().isOk())
				.andExpect(jsonPath("$.data.role").value("VIEWER"));

		JsonNode viewerSession = json(post("/api/workspaces/" + tenantId + "/switch")
				.header("Authorization", "Bearer " + memberTeamToken), 200).path("data");
		assertThat(viewerSession.path("role").asText()).isEqualTo("viewer");
		assertThat(jwtService.parse(viewerSession.path("token").asText()).get("role", String.class))
				.isEqualTo("viewer");
	}

	@Test
	void teamMembersShareMediaWhilePersonalWorkspaceStaysPrivateAndViewerIsReadOnly() throws Exception {
		JsonNode ownerPersonal = register("scope-owner");
		String tenantId = json(post("/api/workspaces")
				.header("Authorization", bearer(ownerPersonal))
				.contentType(MediaType.APPLICATION_JSON)
				.content("{\"name\":\"共享媒体团队\"}"), 200)
				.path("data").path("tenantId").asText();
		String invitationCode = json(post("/api/workspaces/" + tenantId + "/invitations")
				.header("Authorization", bearer(ownerPersonal)), 200)
				.path("data").path("invitationCode").asText();

		JsonNode memberPersonal = register("scope-member");
		String memberId = memberPersonal.path("userId").asText();
		json(post("/api/workspaces/invitations/accept")
				.header("Authorization", bearer(memberPersonal))
				.contentType(MediaType.APPLICATION_JSON)
				.content(objectMapper.writeValueAsString(Map.of("invitationCode", invitationCode))), 200);
		JsonNode ownerTeam = json(post("/api/workspaces/" + tenantId + "/switch")
				.header("Authorization", bearer(ownerPersonal)), 200).path("data");
		JsonNode memberTeam = json(post("/api/workspaces/" + tenantId + "/switch")
				.header("Authorization", bearer(memberPersonal)), 200).path("data");

		MockMultipartFile file = new MockMultipartFile(
				"file", "team-demo.mp4", "video/mp4", MINIMAL_MP4);
		String taskId = json(multipart("/api/media/upload/file")
				.file(file)
				.header("Authorization", bearer(ownerTeam)), 200)
				.path("data").path("taskId").asText();

		mockMvc.perform(get("/api/workflow/tasks/" + taskId)
						.header("Authorization", bearer(memberTeam)))
				.andExpect(status().isOk())
				.andExpect(jsonPath("$.data.owner").value(ownerPersonal.path("userId").asText()))
				.andExpect(jsonPath("$.data.tenantId").value(tenantId));
		mockMvc.perform(get("/api/workflow/tasks")
						.header("Authorization", bearer(memberPersonal)))
				.andExpect(status().isOk())
				.andExpect(jsonPath("$.data[?(@.taskId == '%s')]".formatted(taskId)).isEmpty());

		json(patch("/api/workspaces/" + tenantId + "/members/" + memberId)
				.header("Authorization", bearer(ownerTeam))
				.contentType(MediaType.APPLICATION_JSON)
				.content("{\"role\":\"VIEWER\"}"), 200);
		JsonNode viewerTeam = json(post("/api/workspaces/" + tenantId + "/switch")
				.header("Authorization", bearer(memberTeam)), 200).path("data");
		mockMvc.perform(get("/api/workflow/tasks/" + taskId)
						.header("Authorization", bearer(viewerTeam)))
				.andExpect(status().isOk());
		mockMvc.perform(multipart("/api/media/upload/file")
						.file(new MockMultipartFile(
								"file", "denied.mp4", "video/mp4", new byte[] {1}))
						.header("Authorization", bearer(viewerTeam)))
				.andExpect(status().isForbidden());
	}

	private JsonNode register(String prefix) throws Exception {
		String username = prefix + "-" + System.nanoTime();
		return json(post("/api/auth/register")
				.contentType(MediaType.APPLICATION_JSON)
				.content(objectMapper.writeValueAsString(Map.of(
						"username", username, "password", "secret123"))), 200).path("data");
	}

	private JsonNode json(org.springframework.test.web.servlet.request.MockHttpServletRequestBuilder request,
			int expectedStatus) throws Exception {
		String content = mockMvc.perform(request)
				.andExpect(status().is(expectedStatus))
				.andReturn().getResponse().getContentAsString();
		return objectMapper.readTree(content);
	}

	private static String bearer(JsonNode session) {
		return "Bearer " + session.path("token").asText();
	}
}
