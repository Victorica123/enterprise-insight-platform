package com.example.videoplatform.auth;

import java.util.Map;
import java.util.UUID;
import java.util.concurrent.ConcurrentHashMap;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.stereotype.Service;

@Service
public class AuthService {

	private final Map<String, UserAccount> users = new ConcurrentHashMap<>();
	private final PasswordEncoder passwordEncoder;
	private final JwtService jwtService;

	public AuthService(PasswordEncoder passwordEncoder, JwtService jwtService) {
		this.passwordEncoder = passwordEncoder;
		this.jwtService = jwtService;
	}

	public AuthDtos.AuthResponse register(AuthDtos.RegisterRequest request) {
		if (users.containsKey(request.username())) {
			throw new IllegalArgumentException("用户名已存在");
		}
		UserAccount user = new UserAccount(UUID.randomUUID().toString(), request.username(), passwordEncoder.encode(request.password()));
		users.put(user.username(), user);
		return new AuthDtos.AuthResponse(user.userId(), user.username(), jwtService.generateToken(user.userId(), user.username()));
	}

	public AuthDtos.AuthResponse login(AuthDtos.LoginRequest request) {
		UserAccount user = users.get(request.username());
		if (user == null || !passwordEncoder.matches(request.password(), user.passwordHash())) {
			throw new IllegalArgumentException("用户名或密码错误");
		}
		return new AuthDtos.AuthResponse(user.userId(), user.username(), jwtService.generateToken(user.userId(), user.username()));
	}

	public record UserAccount(String userId, String username, String passwordHash) {
	}
}
