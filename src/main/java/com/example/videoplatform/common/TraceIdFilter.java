package com.example.videoplatform.common;

import jakarta.servlet.FilterChain;
import jakarta.servlet.ServletException;
import jakarta.servlet.http.HttpServletRequest;
import jakarta.servlet.http.HttpServletResponse;
import java.io.IOException;
import java.util.UUID;
import org.slf4j.MDC;
import org.springframework.core.Ordered;
import org.springframework.core.annotation.Order;
import org.springframework.stereotype.Component;
import org.springframework.web.filter.OncePerRequestFilter;

/**
 * 为每个请求生成/透传 traceId：写入 MDC（日志级别行显示）并回写响应头 X-Trace-Id。
 * 排查线上问题时，用户报一个响应头里的 traceId 即可从日志中拉出该请求的完整链路。
 */
@Component
@Order(Ordered.HIGHEST_PRECEDENCE)
public class TraceIdFilter extends OncePerRequestFilter {

	public static final String TRACE_ID_HEADER = "X-Trace-Id";
	public static final String MDC_KEY = "traceId";

	@Override
	protected void doFilterInternal(HttpServletRequest request, HttpServletResponse response, FilterChain filterChain)
			throws ServletException, IOException {
		String traceId = resolveTraceId(request.getHeader(TRACE_ID_HEADER));
		MDC.put(MDC_KEY, traceId);
		response.setHeader(TRACE_ID_HEADER, traceId);
		try {
			filterChain.doFilter(request, response);
		} finally {
			// 线程池复用线程，必须清理避免串号
			MDC.remove(MDC_KEY);
		}
	}

	private static String resolveTraceId(String incoming) {
		// 信任上游网关传入的合法 id（跨服务串联）；非法值一律换新，防止日志注入
		if (incoming != null && incoming.matches("[0-9a-zA-Z-]{8,36}")) {
			return incoming;
		}
		return UUID.randomUUID().toString().replace("-", "").substring(0, 12);
	}
}
