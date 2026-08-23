package com.example.videoplatform.config;

import com.example.videoplatform.auth.JwtAuthenticationFilter;
import org.springframework.boot.context.properties.EnableConfigurationProperties;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.config.annotation.web.configurers.AbstractHttpConfigurer;
import org.springframework.security.config.http.SessionCreationPolicy;
import org.springframework.security.crypto.bcrypt.BCryptPasswordEncoder;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.security.provisioning.InMemoryUserDetailsManager;
import org.springframework.security.web.SecurityFilterChain;
import org.springframework.security.web.authentication.UsernamePasswordAuthenticationFilter;

@Configuration
@EnableConfigurationProperties(AppProperties.class)
public class SecurityConfig {

	@Bean
	SecurityFilterChain securityFilterChain(HttpSecurity http, JwtAuthenticationFilter jwtAuthenticationFilter) throws Exception {
		return http
				.csrf(AbstractHttpConfigurer::disable)
				.sessionManagement(session -> session.sessionCreationPolicy(SessionCreationPolicy.STATELESS))
				.authorizeHttpRequests(auth -> auth
					.requestMatchers("/", "/index.html", "/app.css", "/app.js", "/vendor/**", "/api/auth/**",
							"/actuator/health", "/swagger-ui/**", "/swagger-ui.html", "/v3/api-docs/**")
							.permitAll()
						// 可观测端点：供 Prometheus 抓取 /actuator/prometheus（P2「MQ 量化验证」）。
						// 自托管内网抓取可直接放行；P5 公网部署时应改由独立 management 端口 + 内网/反代限制，不对公网暴露。
						.requestMatchers("/actuator/prometheus", "/actuator/metrics/**", "/actuator/info")
						.permitAll()
						// 视频流式播放：<video> 无法带 Authorization 头，改用查询参数中的签名播放令牌自校验
						.requestMatchers("/api/media/video/*/stream").permitAll()
						.anyRequest().authenticated())
				.addFilterBefore(jwtAuthenticationFilter, UsernamePasswordAuthenticationFilter.class)
				.build();
	}

	@Bean
	PasswordEncoder passwordEncoder() {
		return new BCryptPasswordEncoder();
	}

	@Bean
	InMemoryUserDetailsManager userDetailsService() {
		return new InMemoryUserDetailsManager();
	}
}
