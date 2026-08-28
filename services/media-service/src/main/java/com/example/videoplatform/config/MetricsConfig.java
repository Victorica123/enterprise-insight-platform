package com.example.videoplatform.config;

import io.micrometer.core.instrument.MeterRegistry;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.boot.actuate.autoconfigure.metrics.MeterRegistryCustomizer;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

/**
 * 指标公共配置。给所有 Micrometer 指标打公共标签，便于 Prometheus/Grafana 做「MQ 开/关」A/B 对比：
 * <ul>
 *   <li>{@code application}——服务名。</li>
 *   <li>{@code mq}——当前是否启用 RocketMQ 异步（{@code app.mq.enabled}）。同一 Prometheus 内按此标签区分两次压测。</li>
 * </ul>
 */
@Configuration
public class MetricsConfig {

	@Bean
	public MeterRegistryCustomizer<MeterRegistry> commonMetricsTags(
			@Value("${spring.application.name:video-platform}") String application,
			@Value("${app.mq.enabled:false}") boolean mqEnabled) {
		return registry -> registry.config().commonTags(
				"application", application,
				"mq", String.valueOf(mqEnabled));
	}
}
