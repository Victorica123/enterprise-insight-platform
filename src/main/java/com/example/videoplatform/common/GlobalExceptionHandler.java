package com.example.videoplatform.common;

import io.jsonwebtoken.JwtException;
import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.ExceptionHandler;
import org.springframework.web.bind.annotation.RestControllerAdvice;

@RestControllerAdvice
public class GlobalExceptionHandler {

	private static final org.slf4j.Logger log = org.slf4j.LoggerFactory.getLogger(GlobalExceptionHandler.class);

	@ExceptionHandler(com.example.videoplatform.workflow.ActiveTaskLimitExceededException.class)
	public ResponseEntity<ApiResponse<Void>> handleActiveTaskLimit(
			com.example.videoplatform.workflow.ActiveTaskLimitExceededException exception) {
		log.warn("用户任务配额已满: active={}, limit={}", exception.getActiveCount(), exception.getLimit());
		return ResponseEntity.status(HttpStatus.TOO_MANY_REQUESTS).body(ApiResponse.fail(exception.getMessage()));
	}

	@ExceptionHandler(IllegalArgumentException.class)
	public ResponseEntity<ApiResponse<Void>> handleIllegalArgument(IllegalArgumentException exception) {
		log.warn("业务参数异常: {}", exception.getMessage());
		return ResponseEntity.badRequest().body(ApiResponse.fail(exception.getMessage()));
	}

	@ExceptionHandler(JwtException.class)
	public ResponseEntity<ApiResponse<Void>> handleJwt(JwtException exception) {
		log.warn("JWT 认证异常: {}", exception.getMessage());
		return ResponseEntity.status(HttpStatus.UNAUTHORIZED).body(ApiResponse.fail(exception.getMessage()));
	}

	@ExceptionHandler(org.springframework.core.task.TaskRejectedException.class)
	public ResponseEntity<ApiResponse<Void>> handleTaskRejected(
			org.springframework.core.task.TaskRejectedException exception) {
		// 过载是可预期的容量边界，不打印重复堆栈；任务已落库，可由 stale-task reaper 补偿。
		log.warn("本地处理队列已满，任务等待自动补偿: {}", exception.getMessage());
		return ResponseEntity.status(HttpStatus.SERVICE_UNAVAILABLE)
				.body(ApiResponse.fail("本地处理队列已满，任务已记录并会自动补偿，请稍后刷新任务列表"));
	}

	@ExceptionHandler(org.springframework.web.server.ResponseStatusException.class)
	public ResponseEntity<ApiResponse<Void>> handleResponseStatus(org.springframework.web.server.ResponseStatusException exception) {
		log.warn("HTTP 状态异常: {} - {}", exception.getStatusCode(), exception.getReason());
		return ResponseEntity.status(exception.getStatusCode()).body(ApiResponse.fail(exception.getReason()));
	}

	@ExceptionHandler(Exception.class)
	public ResponseEntity<ApiResponse<Void>> handleUnknown(Exception exception) {
		// 完整堆栈只写服务端日志；对客户端返回通用提示，避免把内部实现细节（SQL 错误、文件路径、类名）泄漏给调用方。
		log.error("系统内部异常", exception);
		return ResponseEntity.status(HttpStatus.INTERNAL_SERVER_ERROR)
				.body(ApiResponse.fail("服务器内部错误，请稍后重试"));
	}
}
