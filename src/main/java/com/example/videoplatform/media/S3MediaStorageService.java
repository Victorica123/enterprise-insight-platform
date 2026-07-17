package com.example.videoplatform.media;

import com.example.videoplatform.common.StringUtils;
import com.example.videoplatform.config.AppProperties;
import java.io.IOException;
import java.io.InputStream;
import java.net.URI;
import java.net.URLEncoder;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.time.Duration;
import java.time.Instant;
import java.time.ZoneOffset;
import java.time.format.DateTimeFormatter;
import java.util.HexFormat;
import java.util.Optional;
import java.util.TreeMap;
import java.util.UUID;
import javax.crypto.Mac;
import javax.crypto.spec.SecretKeySpec;
import org.springframework.boot.autoconfigure.condition.ConditionalOnProperty;
import org.springframework.stereotype.Service;

/**
 * 轻量 S3/MinIO 兼容存储实现。
 *
 * <p>为了保持项目在无外网依赖下载时仍可构建，这里用 JDK HttpClient + S3 Signature V4，
 * 不引入 AWS SDK。生产项目可以再替换为官方 SDK；当前抽象边界已经把替换成本压低。
 */
@Service
@ConditionalOnProperty(prefix = "app.storage", name = "type", havingValue = "s3")
public class S3MediaStorageService implements MediaStorageService {

	private static final String PREFIX = "s3://";
	private static final String SERVICE = "s3";
	private static final DateTimeFormatter AMZ_DATE = DateTimeFormatter.ofPattern("yyyyMMdd'T'HHmmss'Z'")
			.withZone(ZoneOffset.UTC);
	private static final DateTimeFormatter DATE_STAMP = DateTimeFormatter.ofPattern("yyyyMMdd")
			.withZone(ZoneOffset.UTC);

	private final AppProperties.Storage.S3 properties;
	private final HttpClient httpClient;

	public S3MediaStorageService(AppProperties appProperties) {
		this.properties = appProperties.getStorage().getS3();
		validateProperties(properties);
		this.httpClient = HttpClient.newBuilder()
				.connectTimeout(Duration.ofSeconds(10))
				.build();
	}

	@Override
	public String saveUpload(String safeFileName, InputStream inputStream) throws IOException {
		Path temp = Files.createTempFile("video-platform-upload-", "-" + safeFileName);
		try {
			Files.copy(inputStream, temp, java.nio.file.StandardCopyOption.REPLACE_EXISTING);
			return saveFile(safeFileName, temp);
		} finally {
			Files.deleteIfExists(temp);
		}
	}

	@Override
	public String saveFile(String safeFileName, Path sourceFile) throws IOException {
		String key = "uploads/" + UUID.randomUUID() + "-" + safeFileName;
		String contentType = contentType(safeFileName);
		byte[] body = Files.readAllBytes(sourceFile);
		URI uri = objectUri(properties.getBucket(), key);
		Instant now = Instant.now();
		String amzDate = AMZ_DATE.format(now);
		String payloadHash = sha256Hex(body);
		String authorization = authorizationHeader("PUT", uri, canonicalObjectPath(properties.getBucket(), key),
				amzDate, DATE_STAMP.format(now),
				payloadHash, contentType);
		HttpRequest request = HttpRequest.newBuilder(uri)
				.timeout(Duration.ofMinutes(5))
				.header("Authorization", authorization)
				.header("Content-Type", contentType)
				.header("x-amz-content-sha256", payloadHash)
				.header("x-amz-date", amzDate)
				.PUT(HttpRequest.BodyPublishers.ofByteArray(body))
				.build();
		sendExpectSuccess(request, "上传对象存储失败");
		return PREFIX + properties.getBucket() + "/" + key;
	}

	@Override
	public DirectUploadTarget createDirectUploadTarget(String safeFileName, Duration expiresIn) {
		String key = "uploads/direct/" + UUID.randomUUID() + "-" + safeFileName;
		S3Location location = new S3Location(properties.getBucket(), key);
		return new DirectUploadTarget(PREFIX + properties.getBucket() + "/" + key,
				createPresignedUrl("PUT", location, expiresIn, true), Instant.now().plus(expiresIn));
	}

	@Override
	public boolean objectExists(String storagePath) throws IOException {
		S3Location location = parse(storagePath);
		HttpRequest request = HttpRequest.newBuilder(URI.create(createPresignedUrl("HEAD", location, Duration.ofMinutes(5))))
				.timeout(Duration.ofSeconds(10))
				.method("HEAD", HttpRequest.BodyPublishers.noBody())
				.build();
		try {
			HttpResponse<Void> response = httpClient.send(request, HttpResponse.BodyHandlers.discarding());
			if (response.statusCode() == 404) {
				return false;
			}
			if (response.statusCode() >= 200 && response.statusCode() < 300) {
				return true;
			}
			throw new IllegalStateException("检查对象存储文件失败: HTTP " + response.statusCode());
		} catch (InterruptedException e) {
			Thread.currentThread().interrupt();
			throw new IOException("检查对象存储文件被中断", e);
		}
	}

	@Override
	public ResolvedMedia resolveForProcessing(String storagePath) throws IOException {
		S3Location location = parse(storagePath);
		Path temp = Files.createTempFile("video-platform-media-", "-" + Path.of(location.key()).getFileName());
		HttpRequest request = HttpRequest.newBuilder(URI.create(createPresignedUrl("GET", location, Duration.ofMinutes(30))))
				.timeout(Duration.ofMinutes(5))
				.GET()
				.build();
		try {
			HttpResponse<Path> response = httpClient.send(request, HttpResponse.BodyHandlers.ofFile(temp));
			if (response.statusCode() < 200 || response.statusCode() >= 300) {
				Files.deleteIfExists(temp);
				throw new IllegalStateException("下载对象存储文件失败: HTTP " + response.statusCode());
			}
			return new ResolvedMedia(temp, true);
		} catch (InterruptedException e) {
			Thread.currentThread().interrupt();
			Files.deleteIfExists(temp);
			throw new IOException("下载对象存储文件被中断", e);
		}
	}

	@Override
	public Optional<String> createPlaybackRedirectUrl(String storagePath, Duration expiresIn) {
		if (!storagePath.startsWith(PREFIX)) {
			return Optional.empty();
		}
		return Optional.of(createPresignedUrl("GET", parse(storagePath), expiresIn, true));
	}

	@Override
	public Path requireLocalPath(String storagePath) {
		throw new IllegalStateException("对象存储文件不支持本地路径访问: " + storagePath);
	}

	private void sendExpectSuccess(HttpRequest request, String message) throws IOException {
		try {
			HttpResponse<String> response = httpClient.send(request, HttpResponse.BodyHandlers.ofString());
			if (response.statusCode() < 200 || response.statusCode() >= 300) {
				throw new IllegalStateException(message + ": HTTP " + response.statusCode() + " " + response.body());
			}
		} catch (InterruptedException e) {
			Thread.currentThread().interrupt();
			throw new IOException(message + "：请求被中断", e);
		}
	}

	private String authorizationHeader(String method, URI uri, String canonicalObjectPath, String amzDate, String dateStamp,
			String payloadHash, String contentType) {
		String canonicalHeaders = "content-type:" + contentType + "\n"
				+ "host:" + uri.getHost() + hostPort(uri) + "\n"
				+ "x-amz-content-sha256:" + payloadHash + "\n"
				+ "x-amz-date:" + amzDate + "\n";
		String signedHeaders = "content-type;host;x-amz-content-sha256;x-amz-date";
		String canonicalRequest = method + "\n" + canonicalObjectPath + "\n\n" + canonicalHeaders + "\n"
				+ signedHeaders + "\n" + payloadHash;
		String credentialScope = dateStamp + "/" + properties.getRegion() + "/" + SERVICE + "/aws4_request";
		String stringToSign = "AWS4-HMAC-SHA256\n" + amzDate + "\n" + credentialScope + "\n"
				+ sha256Hex(canonicalRequest.getBytes(StandardCharsets.UTF_8));
		String signature = HexFormat.of().formatHex(signingKey(dateStamp).doFinal(
				stringToSign.getBytes(StandardCharsets.UTF_8)));
		return "AWS4-HMAC-SHA256 Credential=" + properties.getAccessKey() + "/" + credentialScope
				+ ", SignedHeaders=" + signedHeaders + ", Signature=" + signature;
	}

	private String createPresignedUrl(String method, S3Location location, Duration expiresIn) {
		return createPresignedUrl(method, location, expiresIn, false);
	}

	private String createPresignedUrl(String method, S3Location location, Duration expiresIn, boolean browserVisible) {
		Instant now = Instant.now();
		String amzDate = AMZ_DATE.format(now);
		String dateStamp = DATE_STAMP.format(now);
		String credentialScope = dateStamp + "/" + properties.getRegion() + "/" + SERVICE + "/aws4_request";
		TreeMap<String, String> query = new TreeMap<>();
		query.put("X-Amz-Algorithm", "AWS4-HMAC-SHA256");
		query.put("X-Amz-Credential", properties.getAccessKey() + "/" + credentialScope);
		query.put("X-Amz-Date", amzDate);
		query.put("X-Amz-Expires", String.valueOf(Math.max(1, expiresIn.toSeconds())));
		query.put("X-Amz-SignedHeaders", "host");

		URI uri = objectUri(location.bucket(), location.key(), browserVisible);
		String canonicalQuery = canonicalQuery(query);
		String canonicalRequest = method + "\n" + canonicalObjectPath(location.bucket(), location.key()) + "\n" + canonicalQuery + "\n"
				+ "host:" + uri.getHost() + hostPort(uri) + "\n\nhost\nUNSIGNED-PAYLOAD";
		String stringToSign = "AWS4-HMAC-SHA256\n" + amzDate + "\n" + credentialScope + "\n"
				+ sha256Hex(canonicalRequest.getBytes(StandardCharsets.UTF_8));
		String signature = HexFormat.of().formatHex(signingKey(dateStamp).doFinal(
				stringToSign.getBytes(StandardCharsets.UTF_8)));
		return uri + "?" + canonicalQuery + "&X-Amz-Signature=" + signature;
	}

	private URI objectUri(String bucket, String key) {
		return objectUri(bucket, key, false);
	}

	private URI objectUri(String bucket, String key, boolean browserVisible) {
		String endpoint = StringUtils.trimTrailingSlash(endpoint(browserVisible));
		if (properties.isPathStyleAccess()) {
			return URI.create(endpoint + "/" + bucket + canonicalUri(key));
		}
		URI base = URI.create(endpoint);
		return URI.create(base.getScheme() + "://" + bucket + "." + base.getAuthority() + canonicalUri(key));
	}

	private String endpoint(boolean browserVisible) {
		if (browserVisible && !StringUtils.isBlank(properties.getPublicEndpoint())) {
			return properties.getPublicEndpoint();
		}
		return properties.getEndpoint();
	}

	private String canonicalObjectPath(String bucket, String key) {
		if (properties.isPathStyleAccess()) {
			return "/" + encode(bucket) + canonicalUri(key);
		}
		return canonicalUri(key);
	}

	private Mac signingKey(String dateStamp) {
		byte[] kDate = hmac(("AWS4" + properties.getSecretKey()).getBytes(StandardCharsets.UTF_8), dateStamp);
		byte[] kRegion = hmac(kDate, properties.getRegion());
		byte[] kService = hmac(kRegion, SERVICE);
		byte[] kSigning = hmac(kService, "aws4_request");
		try {
			Mac mac = Mac.getInstance("HmacSHA256");
			mac.init(new SecretKeySpec(kSigning, "HmacSHA256"));
			return mac;
		} catch (Exception e) {
			throw new IllegalStateException("初始化 S3 签名失败", e);
		}
	}

	private static byte[] hmac(byte[] key, String data) {
		try {
			Mac mac = Mac.getInstance("HmacSHA256");
			mac.init(new SecretKeySpec(key, "HmacSHA256"));
			return mac.doFinal(data.getBytes(StandardCharsets.UTF_8));
		} catch (Exception e) {
			throw new IllegalStateException("计算 S3 签名失败", e);
		}
	}

	private static String sha256Hex(byte[] data) {
		try {
			return HexFormat.of().formatHex(java.security.MessageDigest.getInstance("SHA-256").digest(data));
		} catch (java.security.NoSuchAlgorithmException e) {
			throw new IllegalStateException("SHA-256 不可用", e);
		}
	}

	private static String canonicalQuery(TreeMap<String, String> query) {
		return query.entrySet().stream()
				.map(entry -> encode(entry.getKey()) + "=" + encode(entry.getValue()))
				.collect(java.util.stream.Collectors.joining("&"));
	}

	private static String canonicalUri(String key) {
		return "/" + java.util.Arrays.stream(key.split("/"))
				.map(S3MediaStorageService::encode)
				.collect(java.util.stream.Collectors.joining("/"));
	}

	private static String encode(String value) {
		return URLEncoder.encode(value, StandardCharsets.UTF_8).replace("+", "%20")
				.replace("%7E", "~");
	}

	private static String hostPort(URI uri) {
		int port = uri.getPort();
		if (port == -1 || (uri.getScheme().equals("http") && port == 80)
				|| (uri.getScheme().equals("https") && port == 443)) {
			return "";
		}
		return ":" + port;
	}

	private static void validateProperties(AppProperties.Storage.S3 properties) {
		if (StringUtils.isBlank(properties.getEndpoint())) {
			throw new IllegalArgumentException("app.storage.s3.endpoint 不能为空");
		}
		if (StringUtils.isBlank(properties.getBucket())) {
			throw new IllegalArgumentException("app.storage.s3.bucket 不能为空");
		}
		if (StringUtils.isBlank(properties.getAccessKey()) || StringUtils.isBlank(properties.getSecretKey())) {
			throw new IllegalArgumentException("app.storage.s3.access-key / secret-key 不能为空");
		}
	}

	private static S3Location parse(String storagePath) {
		if (!storagePath.startsWith(PREFIX)) {
			throw new IllegalArgumentException("不是 S3 存储路径: " + storagePath);
		}
		String value = storagePath.substring(PREFIX.length());
		int slash = value.indexOf('/');
		if (slash <= 0 || slash == value.length() - 1) {
			throw new IllegalArgumentException("S3 存储路径格式错误: " + storagePath);
		}
		return new S3Location(value.substring(0, slash), value.substring(slash + 1));
	}

	private static String contentType(String fileName) {
		String lower = fileName.toLowerCase();
		if (lower.endsWith(".mp4") || lower.endsWith(".m4v")) {
			return "video/mp4";
		}
		if (lower.endsWith(".webm")) {
			return "video/webm";
		}
		if (lower.endsWith(".mov")) {
			return "video/quicktime";
		}
		if (lower.endsWith(".mkv")) {
			return "video/x-matroska";
		}
		return "application/octet-stream";
	}

	private record S3Location(String bucket, String key) {
	}
}
