package com.example.videoplatform.config;

import org.springframework.boot.context.properties.ConfigurationProperties;

@ConfigurationProperties(prefix = "app.quota")
public class QuotaProperties {
	/** 0 表示不限制；生产小范围试用建议配置为 5-10。 */
	private int maxActiveTasksPerUser;

	public int getMaxActiveTasksPerUser() {
		return maxActiveTasksPerUser;
	}

	public void setMaxActiveTasksPerUser(int maxActiveTasksPerUser) {
		this.maxActiveTasksPerUser = maxActiveTasksPerUser;
	}
}
