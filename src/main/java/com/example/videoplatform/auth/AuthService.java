package com.example.videoplatform.auth;

import java.util.UUID;

import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class AuthService {

	private final UserAccountRepository userRepository;
	private final PasswordEncoder passwordEncoder;
	private final JwtService jwtService;

	public AuthService(UserAccountRepository userRepository, PasswordEncoder passwordEncoder, JwtService jwtService) {
		this.userRepository = userRepository;
		this.passwordEncoder = passwordEncoder;
		this.jwtService = jwtService;
	}

	@Transactional
	public AuthDtos.AuthResponse register(AuthDtos.RegisterRequest request) {
		if (userRepository.existsByUsername(request.username())) {
			throw new IllegalArgumentException("用户名已存在");
		}
		UserAccount user = new UserAccount(UUID.randomUUID().toString(), request.username(), passwordEncoder.encode(request.password()));
		userRepository.save(user);
		return new AuthDtos.AuthResponse(user.getUserId(), user.getUsername(), jwtService.generateToken(user.getUserId(), user.getUsername()));
	}

	@Transactional(readOnly = true)
	public AuthDtos.AuthResponse login(AuthDtos.LoginRequest request) {
		UserAccount user = userRepository.findByUsername(request.username())
				.orElseThrow(() -> new IllegalArgumentException("用户名或密码错误"));
		if (!passwordEncoder.matches(request.password(), user.getPasswordHash())) {
			throw new IllegalArgumentException("用户名或密码错误");
		}
		return new AuthDtos.AuthResponse(user.getUserId(), user.getUsername(), jwtService.generateToken(user.getUserId(), user.getUsername()));
	}
}
