package com.example.videoplatform.config;

import org.springframework.boot.context.properties.ConfigurationProperties;

@ConfigurationProperties(prefix = "app.mq")
public class MqProperties extends FeatureProperties {
	private int consumerThreads = 4;

	public int getConsumerThreads() {
		return consumerThreads;
	}

	public void setConsumerThreads(int consumerThreads) {
		this.consumerThreads = consumerThreads;
	}
}
