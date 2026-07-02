package com.example.videoplatform.workflow;

import io.micrometer.core.instrument.MeterRegistry;
import io.micrometer.core.instrument.Timer;
import java.time.Duration;
import java.time.Instant;
import org.springframework.stereotype.Component;

/**
 * 工作流处理链路的业务指标（Micrometer）。集中定义指标名与标签，由 Prometheus 抓取、Grafana 展示。
 *
 * <p>P2「MQ 量化验证」用它对比 {@code app.mq.enabled} 开/关：
 * <ul>
 *   <li>{@value #PROCESSING_TIMER}（Timer, tag path/result）——单次处理耗时，区分去重/standalone/单飞路径。</li>
 *   <li>{@value #E2E_TIMER}（Timer, tag result）——任务端到端耗时（createdAt→完成），反映积压导致的排队延迟。</li>
 *   <li>{@value #SKIP_COUNTER}（Counter, tag reason）——被去重/幂等/单飞省下的处理次数。</li>
 * </ul>
 *
 * <p>另有两类指标无需本类埋点即可获得：<b>接口响应时间</b>由 actuator 自带的
 * {@code http.server.requests} 提供；<b>线程池积压/拒绝</b>由 Spring Boot 自动为
 * {@code videoTaskExecutor} 绑定的 {@code executor.queued/active/rejected/completed} 提供。
 * 所有指标带公共标签 {@code mq=true|false}（见 {@code MetricsConfig}），可在同一 Prometheus 内做 A/B 对比。
 */
@Component
public class WorkflowMetrics {

	static final String PROCESSING_TIMER = "video.task.processing";
	static final String E2E_TIMER = "video.task.e2e";
	static final String SKIP_COUNTER = "video.task.skipped";

	private final MeterRegistry registry;

	public WorkflowMetrics(MeterRegistry registry) {
		this.registry = registry;
	}

	/** 开始一次处理计时；与 {@link #stopProcessing} 配对。 */
	public Timer.Sample startProcessing() {
		return Timer.start(registry);
	}

	/**
	 * 结束处理计时并记录。
	 *
	 * @param path   处理路径：dedup（去重命中）/ standalone（无指纹单任务）/ single_flight（内容单飞）
	 * @param result 结果：completed / failed
	 */
	public void stopProcessing(Timer.Sample sample, String path, String result) {
		sample.stop(registry.timer(PROCESSING_TIMER, "path", path, "result", result));
	}

	/**
	 * 记录任务端到端耗时（入队 createdAt → 到达终态）。这是「MQ 削峰」最直观的对比维度：
	 * 高并发下本地 @Async 线程池积压会拉高该值，MQ 由 broker 缓冲则相对平稳。
	 */
	public void recordEndToEnd(Instant createdAt, String result) {
		if (createdAt == null) {
			return;
		}
		registry.timer(E2E_TIMER, "result", result).record(Duration.between(createdAt, Instant.now()));
	}

	/** 记录一次被跳过的处理（去重/幂等/单飞抢锁失败），用于量化这些机制省下的重复处理量。 */
	public void incrementSkip(String reason) {
		registry.counter(SKIP_COUNTER, "reason", reason).increment();
	}
}
