package com.example.videoplatform.media;

import com.example.videoplatform.common.ApiResponse;
import jakarta.validation.Valid;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.security.core.Authentication;
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

	public MediaController(SingleUploadService singleUploadService,
			@Autowired(required = false) ChunkUploadService chunkUploadService) {
		this.singleUploadService = singleUploadService;
		this.chunkUploadService = chunkUploadService;
	}

	@PostMapping("/file")
	public ApiResponse<MediaDtos.SingleUploadResponse> uploadSingleFile(Authentication authentication,
			@RequestPart MultipartFile file) {
		return ApiResponse.ok(singleUploadService.uploadSingleFile(authentication.getName(), file));
	}

	@PostMapping("/init")
	public ResponseEntity<ApiResponse<MediaDtos.InitUploadResponse>> initUpload(Authentication authentication,
			@Valid @RequestBody MediaDtos.InitUploadRequest request) {
		ensureChunkUploadServiceAvailable();
		return ResponseEntity.ok(ApiResponse.ok(chunkUploadService.initUpload(authentication.getName(), request)));
	}

	@PostMapping("/chunk")
	public ResponseEntity<ApiResponse<MediaDtos.ChunkUploadResponse>> uploadChunk(Authentication authentication,
			@RequestParam String uploadId, @RequestParam int chunkIndex, @RequestPart MultipartFile file) {
		ensureChunkUploadServiceAvailable();
		return ResponseEntity.ok(ApiResponse.ok(
				chunkUploadService.uploadChunk(authentication.getName(), uploadId, chunkIndex, file)));
	}

	@PostMapping("/merge")
	public ResponseEntity<ApiResponse<MediaDtos.MergeResponse>> mergeChunks(Authentication authentication,
			@Valid @RequestBody MediaDtos.MergeRequest request) {
		ensureChunkUploadServiceAvailable();
		return ResponseEntity.ok(ApiResponse.ok(chunkUploadService.mergeChunks(authentication.getName(), request)));
	}

	private void ensureChunkUploadServiceAvailable() {
		if (chunkUploadService == null) {
			throw new ResponseStatusException(HttpStatus.SERVICE_UNAVAILABLE, "分片上传未启用（Redis 不可用）");
		}
	}
}
