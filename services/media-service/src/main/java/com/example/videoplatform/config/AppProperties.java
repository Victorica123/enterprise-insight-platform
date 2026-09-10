package com.example.videoplatform.config;

import java.time.Duration;
import java.util.ArrayList;
import java.util.List;
import org.springframework.boot.context.properties.ConfigurationProperties;

@ConfigurationProperties(prefix = "app")
public class AppProperties {

	private final Jwt jwt = new Jwt();
	private final Oidc oidc = new Oidc();
	private final Storage storage = new Storage();
	private final Workflow workflow = new Workflow();
	private final Quota quota = new Quota();
	private final Mq mq = new Mq();
	private final Transcript transcript = new Transcript();
	private final Summary summary = new Summary();
	private final Security security = new Security();
	private final Integration integration = new Integration();
	private final ModelEgress modelEgress = new ModelEgress();
	private final Retention retention = new Retention();

	public Jwt getJwt() {
		return jwt;
	}

	public Oidc getOidc() {
		return oidc;
	}

	public Storage getStorage() {
		return storage;
	}

	public Workflow getWorkflow() {
		return workflow;
	}

	public Quota getQuota() {
		return quota;
	}

	public Mq getMq() {
		return mq;
	}

	public Transcript getTranscript() {
		return transcript;
	}

	public Summary getSummary() {
		return summary;
	}

	public Security getSecurity() {
		return security;
	}

	public Integration getIntegration() {
		return integration;
	}

	public ModelEgress getModelEgress() {
		return modelEgress;
	}

	public Retention getRetention() {
		return retention;
	}

	public static class Integration {
		private final Agent agent = new Agent();

		public Agent getAgent() {
			return agent;
		}

		public static class Agent extends Feature {
			private String baseUrl = "http://127.0.0.1:8000";
			private String serviceToken;
			private long dispatchIntervalMs = 2_000;
			private int maxAttempts = 10;
			private long claimLeaseDurationMs = 30_000;

			public String getBaseUrl() {
				return baseUrl;
			}

			public void setBaseUrl(String baseUrl) {
				this.baseUrl = baseUrl;
			}

			public String getServiceToken() {
				return serviceToken;
			}

			public void setServiceToken(String serviceToken) {
				this.serviceToken = serviceToken;
			}

			public long getDispatchIntervalMs() {
				return dispatchIntervalMs;
			}

			public void setDispatchIntervalMs(long dispatchIntervalMs) {
				this.dispatchIntervalMs = dispatchIntervalMs;
			}

			public int getMaxAttempts() {
				return maxAttempts;
			}

			public void setMaxAttempts(int maxAttempts) {
				this.maxAttempts = maxAttempts;
			}

			public long getClaimLeaseDurationMs() {
				return claimLeaseDurationMs;
			}

			public void setClaimLeaseDurationMs(long claimLeaseDurationMs) {
				this.claimLeaseDurationMs = claimLeaseDurationMs;
			}
		}
	}

	/** 认证相关防护配置。 */
	public static class Security {
		private final LoginRateLimit loginRateLimit = new LoginRateLimit();
		private boolean localAuthEnabled = true;

		public LoginRateLimit getLoginRateLimit() {
			return loginRateLimit;
		}

		public boolean isLocalAuthEnabled() {
			return localAuthEnabled;
		}

		public void setLocalAuthEnabled(boolean localAuthEnabled) {
			this.localAuthEnabled = localAuthEnabled;
		}

		/** 滑动窗口：窗口内失败次数达到上限后拒绝，窗口滑出后自动恢复。 */
		public static class LoginRateLimit {
			private int maxAttempts = 5;
			private int windowSeconds = 300;

			public int getMaxAttempts() {
				return maxAttempts;
			}

			public void setMaxAttempts(int maxAttempts) {
				this.maxAttempts = maxAttempts;
			}

			public int getWindowSeconds() {
				return windowSeconds;
			}

			public void setWindowSeconds(int windowSeconds) {
				this.windowSeconds = windowSeconds;
			}
		}
	}

	public static class Jwt {
		private String secret;
		private String algorithm = "HS256";
		private String privateKeyPath;
		private String publicKeyPath;
		private String keyId = "platform-1";
		private long expirationSeconds;
		private String issuer = "enterprise-insight";
		private String audience = "enterprise-insight-api";

		public String getSecret() {
			return secret;
		}

		public void setSecret(String secret) {
			this.secret = secret;
		}

		public String getAlgorithm() {
			return algorithm;
		}

		public void setAlgorithm(String algorithm) {
			this.algorithm = algorithm;
		}

		public String getPrivateKeyPath() {
			return privateKeyPath;
		}

		public void setPrivateKeyPath(String privateKeyPath) {
			this.privateKeyPath = privateKeyPath;
		}

		public String getPublicKeyPath() {
			return publicKeyPath;
		}

		public void setPublicKeyPath(String publicKeyPath) {
			this.publicKeyPath = publicKeyPath;
		}

		public String getKeyId() {
			return keyId;
		}

		public void setKeyId(String keyId) {
			this.keyId = keyId;
		}

		public long getExpirationSeconds() {
			return expirationSeconds;
		}

		public void setExpirationSeconds(long expirationSeconds) {
			this.expirationSeconds = expirationSeconds;
		}

		public String getIssuer() {
			return issuer;
		}

		public void setIssuer(String issuer) {
			this.issuer = issuer;
		}

		public String getAudience() {
			return audience;
		}

		public void setAudience(String audience) {
			this.audience = audience;
		}
	}

	public static class Storage {
		private String basePath;
		private String type = "local";
		private final S3 s3 = new S3();
		private final Cleanup cleanup = new Cleanup();

		public String getBasePath() {
			return basePath;
		}

		public void setBasePath(String basePath) {
			this.basePath = basePath;
		}

		public String getType() {
			return type;
		}

		public void setType(String type) {
			this.type = type;
		}

		public S3 getS3() {
			return s3;
		}

		public Cleanup getCleanup() {
			return cleanup;
		}

		public static class Cleanup {
			private Duration chunkRetention = Duration.ofHours(24);

			public Duration getChunkRetention() {
				return chunkRetention;
			}

			public void setChunkRetention(Duration chunkRetention) {
				this.chunkRetention = chunkRetention;
			}
		}

		public static class S3 {
			private String endpoint;
			private String publicEndpoint;
			private String region = "us-east-1";
			private String bucket = "video-platform";
			private String accessKey;
			private String secretKey;
			private boolean pathStyleAccess = true;

			public String getEndpoint() {
				return endpoint;
			}

			public void setEndpoint(String endpoint) {
				this.endpoint = endpoint;
			}

			public String getPublicEndpoint() {
				return publicEndpoint;
			}

			public void setPublicEndpoint(String publicEndpoint) {
				this.publicEndpoint = publicEndpoint;
			}

			public String getRegion() {
				return region;
			}

			public void setRegion(String region) {
				this.region = region;
			}

			public String getBucket() {
				return bucket;
			}

			public void setBucket(String bucket) {
				this.bucket = bucket;
			}

			public String getAccessKey() {
				return accessKey;
			}

			public void setAccessKey(String accessKey) {
				this.accessKey = accessKey;
			}

			public String getSecretKey() {
				return secretKey;
			}

			public void setSecretKey(String secretKey) {
				this.secretKey = secretKey;
			}

			public boolean isPathStyleAccess() {
				return pathStyleAccess;
			}

			public void setPathStyleAccess(boolean pathStyleAccess) {
				this.pathStyleAccess = pathStyleAccess;
			}
		}
	}

	public static class Workflow {
		private Duration staleTaskTimeout = Duration.ofHours(1);
		private Duration taskLeaseDuration = Duration.ofMinutes(15);
		private long dispatchIntervalMs = 250;
		private long dispatchClaimLeaseMs = 30_000;

		public Duration getStaleTaskTimeout() {
			return staleTaskTimeout;
		}

		public void setStaleTaskTimeout(Duration staleTaskTimeout) {
			this.staleTaskTimeout = staleTaskTimeout;
		}

		public Duration getTaskLeaseDuration() {
			return taskLeaseDuration;
		}

		public void setTaskLeaseDuration(Duration taskLeaseDuration) {
			this.taskLeaseDuration = taskLeaseDuration;
		}

		public long getDispatchIntervalMs() {
			return dispatchIntervalMs;
		}

		public void setDispatchIntervalMs(long dispatchIntervalMs) {
			this.dispatchIntervalMs = dispatchIntervalMs;
		}

		public long getDispatchClaimLeaseMs() {
			return dispatchClaimLeaseMs;
		}

		public void setDispatchClaimLeaseMs(long dispatchClaimLeaseMs) {
			this.dispatchClaimLeaseMs = dispatchClaimLeaseMs;
		}
	}

	public static class Oidc extends Feature {
		private String issuerUri;
		private String jwkSetUri;
		private String audience = "enterprise-insight-web";
		private String usernameClaim = "preferred_username";

		public String getIssuerUri() {
			return issuerUri;
		}

		public void setIssuerUri(String issuerUri) {
			this.issuerUri = issuerUri;
		}

		public String getJwkSetUri() {
			return jwkSetUri;
		}

		public void setJwkSetUri(String jwkSetUri) {
			this.jwkSetUri = jwkSetUri;
		}

		public String getAudience() {
			return audience;
		}

		public void setAudience(String audience) {
			this.audience = audience;
		}

		public String getUsernameClaim() {
			return usernameClaim;
		}

		public void setUsernameClaim(String usernameClaim) {
			this.usernameClaim = usernameClaim;
		}
	}

	public static class Quota {
		/** 0 表示不限制；生产小范围试用建议配置为 5-10。 */
		private int maxActiveTasksPerUser;

		public int getMaxActiveTasksPerUser() {
			return maxActiveTasksPerUser;
		}

		public void setMaxActiveTasksPerUser(int maxActiveTasksPerUser) {
			this.maxActiveTasksPerUser = maxActiveTasksPerUser;
		}
	}

	public static class Mq extends Feature {
		private int consumerThreads = 4;

		public int getConsumerThreads() {
			return consumerThreads;
		}

		public void setConsumerThreads(int consumerThreads) {
			this.consumerThreads = consumerThreads;
		}
	}

	public static class Feature {
		private boolean enabled;

		public boolean isEnabled() {
			return enabled;
		}

		public void setEnabled(boolean enabled) {
			this.enabled = enabled;
		}
	}

	public static class ModelEgress {
		private String policy = "allow";
		private List<String> allowedTenants = new ArrayList<>();

		public String getPolicy() {
			return policy;
		}

		public void setPolicy(String policy) {
			this.policy = policy;
		}

		public List<String> getAllowedTenants() {
			return allowedTenants;
		}

		public void setAllowedTenants(List<String> allowedTenants) {
			this.allowedTenants = allowedTenants == null ? new ArrayList<>() : new ArrayList<>(allowedTenants);
		}
	}

	public static class Retention extends Feature {
		private int mediaDays = 30;
		private int transcriptDays = 180;
		private int auditDays = 365;
		private int batchSize = 200;

		public int getMediaDays() {
			return mediaDays;
		}

		public void setMediaDays(int mediaDays) {
			this.mediaDays = mediaDays;
		}

		public int getTranscriptDays() {
			return transcriptDays;
		}

		public void setTranscriptDays(int transcriptDays) {
			this.transcriptDays = transcriptDays;
		}

		public int getAuditDays() {
			return auditDays;
		}

		public void setAuditDays(int auditDays) {
			this.auditDays = auditDays;
		}

		public int getBatchSize() {
			return batchSize;
		}

		public void setBatchSize(int batchSize) {
			this.batchSize = batchSize;
		}
	}

	public static class Transcript extends Feature {
		/**
		 * Mock 转写的模拟处理耗时（毫秒），默认 0（即刻返回，不影响正常使用）。
		 * 压测（P2 MQ 量化验证）时设为秒级，还原真实转写的慢消费者特征——否则
		 * Mock 即刻返回，线程池永不饱和，本地 @Async 与 MQ 削峰的差异无法测出。
		 */
		private long mockDelayMs;

		private final Whisper whisper = new Whisper();

		public long getMockDelayMs() {
			return mockDelayMs;
		}

		public void setMockDelayMs(long mockDelayMs) {
			this.mockDelayMs = mockDelayMs;
		}

		public Whisper getWhisper() {
			return whisper;
		}

		public static class Whisper {
			private String apiBaseUrl;
			private String apiKey;
			private String model = "whisper-1";
			private String ffmpegPath = "ffmpeg";

			public String getApiBaseUrl() {
				return apiBaseUrl;
			}

			public void setApiBaseUrl(String apiBaseUrl) {
				this.apiBaseUrl = apiBaseUrl;
			}

			public String getApiKey() {
				return apiKey;
			}

			public void setApiKey(String apiKey) {
				this.apiKey = apiKey;
			}

			public String getModel() {
				return model;
			}

			public void setModel(String model) {
				this.model = model;
			}

			public String getFfmpegPath() {
				return ffmpegPath;
			}

			public void setFfmpegPath(String ffmpegPath) {
				this.ffmpegPath = ffmpegPath;
			}
		}
	}

	public static class Summary extends Feature {
		private final Llm llm = new Llm();

		public Llm getLlm() {
			return llm;
		}

		public static class Llm {
			private String apiBaseUrl;
			private String apiKey;
			private String model = "gpt-4o-mini";
			private String systemPrompt = "请将以下视频转写内容总结为3-5条要点，并给出一个简短结论。";

			public String getApiBaseUrl() {
				return apiBaseUrl;
			}

			public void setApiBaseUrl(String apiBaseUrl) {
				this.apiBaseUrl = apiBaseUrl;
			}

			public String getApiKey() {
				return apiKey;
			}

			public void setApiKey(String apiKey) {
				this.apiKey = apiKey;
			}

			public String getModel() {
				return model;
			}

			public void setModel(String model) {
				this.model = model;
			}

			public String getSystemPrompt() {
				return systemPrompt;
			}

			public void setSystemPrompt(String systemPrompt) {
				this.systemPrompt = systemPrompt;
			}
		}
	}
}
