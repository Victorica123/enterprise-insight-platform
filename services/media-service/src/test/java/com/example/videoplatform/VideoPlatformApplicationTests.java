package com.example.videoplatform;

import org.junit.jupiter.api.Test;
import org.springframework.boot.test.context.SpringBootTest;

@SpringBootTest(properties = {
		"app.redis.enabled=false",
		"app.mq.enabled=false",
		"spring.docker.compose.enabled=false",
		"spring.autoconfigure.exclude="
				+ "org.apache.rocketmq.spring.autoconfigure.RocketMQAutoConfiguration,"
				+ "org.springframework.boot.autoconfigure.data.redis.RedisAutoConfiguration,"
				+ "org.springframework.boot.autoconfigure.data.redis.RedisRepositoriesAutoConfiguration"
})
class VideoPlatformApplicationTests {

	@Test
	void contextLoads() {
	}
}
