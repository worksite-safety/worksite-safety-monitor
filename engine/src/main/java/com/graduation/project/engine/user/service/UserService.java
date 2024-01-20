package com.graduation.project.engine.user.service;

import com.graduation.project.engine.core.PasswordService;
import com.graduation.project.engine.core.exception.BadRequestException;
import com.graduation.project.engine.core.exception.EntityAlreadyExistsException;
import com.graduation.project.engine.core.exception.EntityNotFoundException;
import com.graduation.project.engine.core.exception.PasswordWrongException;
import com.graduation.project.engine.core.securityConfig.JwtService;
import com.graduation.project.engine.email.service.MailService;
import com.graduation.project.engine.user.model.converter.User2UserResponseDtoConverter;
import com.graduation.project.engine.user.model.request.ChangePasswordRequestDto;
import com.graduation.project.engine.user.model.request.LoginRequestDto;
import com.graduation.project.engine.user.model.request.RegisterRequestDto;
import com.graduation.project.engine.user.model.request.UserUpdateRequestDto;
import com.graduation.project.engine.user.model.response.AuthenticationResponseDto;
import com.graduation.project.engine.user.model.response.UserResponseDto;
import com.graduation.project.engine.user.model.Role;
import com.graduation.project.engine.user.model.Token;
import com.graduation.project.engine.user.model.TokenType;
import com.graduation.project.engine.user.model.User;
import com.graduation.project.engine.user.repository.TokenRepository;
import com.graduation.project.engine.user.repository.UserRepository;
import lombok.RequiredArgsConstructor;
import lombok.SneakyThrows;
import org.springframework.security.authentication.AuthenticationManager;
import org.springframework.security.authentication.UsernamePasswordAuthenticationToken;
import org.springframework.security.core.AuthenticationException;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.stereotype.Service;

import java.time.LocalDateTime;
import java.util.List;

import static com.graduation.project.engine.core.exception.constant.ErrorConstant.*;

@Service
@RequiredArgsConstructor
public class UserService {

  private final UserRepository userRepository;
  private final PasswordEncoder passwordEncoder;
  private final JwtService jwtService;
  private final AuthenticationManager authenticationManager;
  private final TokenRepository tokenRepository;
  private final User2UserResponseDtoConverter user2UserResponseDtoConverter;
  private final PasswordService passwordService;
  private final MailService mailService;

  public AuthenticationResponseDto register(RegisterRequestDto request) {

    userRepository.findByEmail(request.getEmail()).ifPresent(s -> {
      throw new EntityAlreadyExistsException(
          errorMessageParser(USER_EMAIL_ALREADY_EXISTS, request.getEmail()));
    });

    var user = User.builder()
        .firstName(request.getFirstName())
        .lastName(request.getLastName())
        .email(request.getEmail())
        .password(passwordEncoder.encode(request.getPassword()))
        .role(Role.ADMIN)
        .registeredAt(LocalDateTime.now())
        .build();
    var savedUser = userRepository.save(user);
    var jwtToken = jwtService.generateToken(user);
    saveUserToken(savedUser, jwtToken);
    return AuthenticationResponseDto.builder()
        .id(user.getId())
        .token(jwtToken)
        .name(user.getFirstName())
        .role(user.getRole())
        .lastName(user.getLastName())
        .email(user.getEmail())
        .build();
  }

  public AuthenticationResponseDto authenticate(LoginRequestDto request) {

    try {
      authenticationManager.authenticate(
          new UsernamePasswordAuthenticationToken(
              request.getEmail(),
              request.getPassword()
          )
      );
    }catch (AuthenticationException e){

      throw new PasswordWrongException(
          errorMessageParser(USER_PASSWORD_NOT_MATCH, request.getEmail()));

    }

    var user = userRepository.findByEmail(request.getEmail()).orElseThrow();

    var jwtToken = jwtService.generateToken(user);

    revokeAllUserTokens(user);
    saveUserToken(user, jwtToken);

    return AuthenticationResponseDto.builder()
        .id(user.getId())
        .token(jwtToken)
        .name(user.getFirstName())
        .role(user.getRole())
        .lastName(user.getLastName())
        .email(user.getEmail())
        .build();
  }

  public List<UserResponseDto> getAllUsers() {
    return user2UserResponseDtoConverter.convert(userRepository.findAll());
  }

  private void saveUserToken(User user, String jwtToken) {
    var token = Token.builder()
        .user(user)
        .token(jwtToken)
        .tokenType(TokenType.BEARER)
        .expired(false)
        .revoked(false)
        .build();
    tokenRepository.save(token);
  }

  private void revokeAllUserTokens(User user) {
    var validUserTokens = tokenRepository.findByUserIdAndExpiredFalseAndRevokedFalse(user.getId());
    if (validUserTokens.isEmpty()) {
      return;
    }
    validUserTokens.forEach(token -> {
      token.setExpired(true);
      token.setRevoked(true);
    });
    tokenRepository.saveAll(validUserTokens);
  }

  @SneakyThrows
  public void forgotPassword(String email) {

    User user = userRepository.findByEmail(email).orElseThrow(
        () -> new EntityNotFoundException(errorMessageParser(USER_NOT_FOUND_MESSAGE, email)));

    String hashedEmail = passwordService.encrypt(email);

    mailService.sendForgotPasswordEmail(user, hashedEmail);
  }

  @SneakyThrows
  public void changePassword(ChangePasswordRequestDto request) {

    String email = passwordService.decrypt(request.getSecretKey());

    User user = userRepository.findByEmail(email).orElseThrow(
        () -> new EntityNotFoundException(errorMessageParser(USER_NOT_FOUND_MESSAGE, email)));

    if (!request.getPassword().equals(request.getConfirmPassword())) {
      throw new BadRequestException(
          errorMessageParser(USER_PASSWORD_NOT_MATCH, request.getPassword()));
    }

    user.setPassword(passwordService.hashPassword(request.getPassword()));
    userRepository.save(user);
  }

  public AuthenticationResponseDto updateUser(UserUpdateRequestDto request, String userId) {

    User user = userRepository.findById(userId).orElseThrow(
        () -> new EntityNotFoundException(
            errorMessageParser(USER_NOT_FOUND_MESSAGE, userId)));

    if (!request.getNewPassword().equals(request.getNewPasswordConfirm())) {
      throw new BadRequestException(
          errorMessageParser(USER_PASSWORD_NOT_MATCH, request.getNewPassword()));
    }

    user.setPassword(passwordService.hashPassword(request.getNewPassword()));

    userRepository.save(user);

    return AuthenticationResponseDto.builder()
        .id(user.getId())
        .name(user.getFirstName())
        .role(user.getRole())
        .lastName(user.getLastName())
        .email(user.getEmail())
        .build();
  }
}
