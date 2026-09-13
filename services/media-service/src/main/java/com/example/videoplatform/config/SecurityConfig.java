package com.example.videoplatform.config;

import com.example.videoplatform.auth.JwtAuthenticationFilter;
import org.springframework.context.annotation.Import;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.config.annotation.web.configurers.AbstractHttpConfigurer;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.http.SessionCreationPolicy;
import org.springframework.security.crypto.bcrypt.BCryptPasswordEncoder;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.security.provisioning.InMemoryUserDetailsManager;
import org.springframework.security.web.SecurityFilterChain;
import org.springframework.security.web.authentication.UsernamePasswordAuthenticationFilter;
import org.springframework.web.cors.CorsConfiguration;
import org.springframework.web.cors.CorsConfigurationSource;
import org.springframework.web.cors.UrlBasedCorsConfigurationSource;

import java.util.List;

@Configuration
@Import(AppConfiguration.class)
public class SecurityConfig {

	@Bean
	SecurityFilterChain securityFilterChain(HttpSecurity http, JwtAuthenticationFilter jwtAuthenticationFilter) throws Exception {
		return http
				.csrf(AbstractHttpConfigurer::disable)
				.cors(Customizer.withDefaults())
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

	/** 本地统一前端验收使用的显式 CORS 白名单；生产同源反代不依赖该配置。 */
	@Bean
	CorsConfigurationSource corsConfigurationSource() {
		CorsConfiguration configuration = new CorsConfiguration();
		configuration.setAllowedOrigins(List.of("http://127.0.0.1:5173", "http://localhost:5173"));
		configuration.setAllowedMethods(List.of("GET", "POST", "PUT", "DELETE", "OPTIONS"));
		configuration.setAllowedHeaders(List.of("Authorization", "Content-Type", "X-Trace-Id"));
		configuration.setExposedHeaders(List.of("X-Trace-Id", "Content-Range", "Accept-Ranges"));
		UrlBasedCorsConfigurationSource source = new UrlBasedCorsConfigurationSource();
		source.registerCorsConfiguration("/**", configuration);
		return source;
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
