package com.example.videoplatform.auth;

import static org.assertj.core.api.Assertions.assertThat;

import com.example.videoplatform.config.AppProperties;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.security.KeyPairGenerator;
import java.util.Base64;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.io.TempDir;

class Rs256JwtServiceTests {

	@TempDir
	Path tempDir;

	@Test
	void signsParsesAndPublishesPublicJwk() throws Exception {
		var generator = KeyPairGenerator.getInstance("RSA");
		generator.initialize(2048);
		var pair = generator.generateKeyPair();
		Path privatePath = tempDir.resolve("private.pem");
		Path publicPath = tempDir.resolve("public.pem");
		writePem(privatePath, "PRIVATE KEY", pair.getPrivate().getEncoded());
		writePem(publicPath, "PUBLIC KEY", pair.getPublic().getEncoded());

		AppProperties properties = new AppProperties();
		properties.getJwt().setAlgorithm("RS256");
		properties.getJwt().setPrivateKeyPath(privatePath.toString());
		properties.getJwt().setPublicKeyPath(publicPath.toString());
		properties.getJwt().setKeyId("pilot-key");
		properties.getJwt().setExpirationSeconds(300);
		JwtService service = new JwtService(properties);
		service.validateJwtConfiguration();

		String token = service.generateAccessToken("user-1", "alice", "tenant-1", "operator", "personal");
		assertThat(service.parse(token).getSubject()).isEqualTo("user-1");
		assertThat(service.parse(token).get("tenant_id", String.class)).isEqualTo("tenant-1");
		assertThat(service.publicJwks().toString()).contains("pilot-key", "RS256", "kty=RSA");
	}

	private void writePem(Path path, String type, byte[] encoded) throws Exception {
		String value = "-----BEGIN " + type + "-----\n"
				+ Base64.getMimeEncoder(64, "\n".getBytes(StandardCharsets.US_ASCII)).encodeToString(encoded)
				+ "\n-----END " + type + "-----\n";
		Files.writeString(path, value, StandardCharsets.US_ASCII);
	}
}
