package com.example.videoplatform.media;

import com.example.videoplatform.common.ApiResponse;
import com.example.videoplatform.auth.WorkspacePrincipal;
import jakarta.validation.Valid;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.security.core.Authentication;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RequestPart;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.multipart.MultipartFile;
import org.springframework.web.server.ResponseStatusException;

@RestController
@RequestMapping("/api/media/upload")
public class MediaController {

	private final SingleUploadService singleUploadService;
	private final ChunkUploadService chunkUploadService;
	private final DirectUploadService directUploadService;

	public MediaController(SingleUploadService singleUploadService,
			@Autowired(required = false) ChunkUploadService chunkUploadService,
			DirectUploadService directUploadService) {
		this.singleUploadService = singleUploadService;
		this.chunkUploadService = chunkUploadService;
		this.directUploadService = directUploadService;
	}

	@PostMapping("/file")
	public ApiResponse<MediaDtos.SingleUploadResponse> uploadSingleFile(Authentication authentication,
			@RequestPart MultipartFile file) {
		WorkspacePrincipal principal = requireWriter(authentication);
		return ApiResponse.ok(singleUploadService.uploadSingleFile(
				principal.userId(), principal.tenantId(), file));
	}

	@PostMapping("/direct/init")
	public ApiResponse<MediaDtos.DirectUploadInitResponse> initDirectUpload(Authentication authentication,
			@Valid @RequestBody MediaDtos.DirectUploadInitRequest request) {
		WorkspacePrincipal principal = requireWriter(authentication);
		return ApiResponse.ok(directUploadService.initDirectUpload(
				principal.userId(), principal.tenantId(), request));
	}

	@PostMapping("/direct/complete")
	public ApiResponse<MediaDtos.DirectUploadCompleteResponse> completeDirectUpload(Authentication authentication,
			@Valid @RequestBody MediaDtos.DirectUploadCompleteRequest request) {
		WorkspacePrincipal principal = requireWriter(authentication);
		return ApiResponse.ok(directUploadService.completeDirectUpload(
				principal.userId(), principal.tenantId(), request));
	}

	@PostMapping("/init")
	public ResponseEntity<ApiResponse<MediaDtos.InitUploadResponse>> initUpload(Authentication authentication,
			@Valid @RequestBody MediaDtos.InitUploadRequest request) {
		ensureChunkUploadServiceAvailable();
		WorkspacePrincipal principal = requireWriter(authentication);
		return ResponseEntity.ok(ApiResponse.ok(chunkUploadService.initUpload(
				principal.userId(), principal.tenantId(), request)));
	}

	@PostMapping("/chunk")
	public ResponseEntity<ApiResponse<MediaDtos.ChunkUploadResponse>> uploadChunk(Authentication authentication,
			@RequestParam String uploadId, @RequestParam int chunkIndex, @RequestPart MultipartFile file) {
		ensureChunkUploadServiceAvailable();
		WorkspacePrincipal principal = requireWriter(authentication);
		return ResponseEntity.ok(ApiResponse.ok(chunkUploadService.uploadChunk(
				principal.userId(), principal.tenantId(), uploadId, chunkIndex, file)));
	}

	@PostMapping("/merge")
	public ResponseEntity<ApiResponse<MediaDtos.MergeResponse>> mergeChunks(Authentication authentication,
			@Valid @RequestBody MediaDtos.MergeRequest request) {
		ensureChunkUploadServiceAvailable();
		WorkspacePrincipal principal = requireWriter(authentication);
		return ResponseEntity.ok(ApiResponse.ok(chunkUploadService.mergeChunks(
				principal.userId(), principal.tenantId(), request)));
	}

	/** 断点续传：前端在续传前查询已上传分片，跳过重复上传。 */
	@GetMapping("/status")
	public ResponseEntity<ApiResponse<MediaDtos.UploadStatusResponse>> uploadStatus(Authentication authentication,
			@RequestParam String uploadId) {
		ensureChunkUploadServiceAvailable();
		WorkspacePrincipal principal = requireWriter(authentication);
		return ResponseEntity.ok(ApiResponse.ok(chunkUploadService.getUploadStatus(
				principal.userId(), principal.tenantId(), uploadId)));
	}

	private void ensureChunkUploadServiceAvailable() {
		if (chunkUploadService == null) {
			throw new ResponseStatusException(HttpStatus.SERVICE_UNAVAILABLE, "分片上传未启用（Redis 不可用）");
		}
	}

	private static WorkspacePrincipal requireWriter(Authentication authentication) {
		WorkspacePrincipal principal = WorkspacePrincipal.require(authentication);
		if (!principal.canWrite()) {
			throw new ResponseStatusException(HttpStatus.FORBIDDEN, "当前角色没有上传权限");
		}
		return principal;
	}
}
