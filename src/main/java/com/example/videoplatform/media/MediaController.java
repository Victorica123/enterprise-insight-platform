package com.example.videoplatform.media;

import com.example.videoplatform.common.ApiResponse;
import jakarta.validation.Valid;
import org.springframework.security.core.Authentication;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RequestPart;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.multipart.MultipartFile;

@RestController
@RequestMapping("/api/media/upload")
public class MediaController {

	private final ChunkUploadService chunkUploadService;

	public MediaController(ChunkUploadService chunkUploadService) {
		this.chunkUploadService = chunkUploadService;
	}

	@PostMapping("/file")
	public ApiResponse<MediaDtos.SingleUploadResponse> uploadSingleFile(Authentication authentication,
			@RequestPart MultipartFile file) {
		return ApiResponse.ok(chunkUploadService.uploadSingleFile(authentication.getName(), file));
	}

	@PostMapping("/init")
	public ApiResponse<MediaDtos.InitUploadResponse> initUpload(Authentication authentication,
			@Valid @RequestBody MediaDtos.InitUploadRequest request) {
		return ApiResponse.ok(chunkUploadService.initUpload(authentication.getName(), request));
	}

	@PostMapping("/chunk")
	public ApiResponse<MediaDtos.ChunkUploadResponse> uploadChunk(@RequestParam String uploadId,
			@RequestParam int chunkIndex, @RequestPart MultipartFile file) {
		return ApiResponse.ok(chunkUploadService.uploadChunk(uploadId, chunkIndex, file));
	}

	@PostMapping("/merge")
	public ApiResponse<MediaDtos.MergeResponse> mergeChunks(Authentication authentication,
			@Valid @RequestBody MediaDtos.MergeRequest request) {
		return ApiResponse.ok(chunkUploadService.mergeChunks(authentication.getName(), request));
	}
}
