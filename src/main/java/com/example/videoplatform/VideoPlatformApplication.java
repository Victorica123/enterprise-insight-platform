package com.example.videoplatform;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.scheduling.annotation.EnableAsync;

@EnableAsync
@SpringBootApplication
public class VideoPlatformApplication {

	public static void main(String[] args) {
		SpringApplication.run(VideoPlatformApplication.class, args);
	}
}
