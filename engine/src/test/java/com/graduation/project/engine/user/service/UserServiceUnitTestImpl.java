package com.graduation.project.engine.user.service;

import static org.hibernate.validator.internal.util.Contracts.assertNotNull;
import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.when;

import com.graduation.project.engine.core.PasswordService;
import com.graduation.project.engine.core.exception.BadRequestException;
import com.graduation.project.engine.core.exception.EntityAlreadyExistsException;
import com.graduation.project.engine.core.exception.EntityNotFoundException;
import com.graduation.project.engine.core.exception.PasswordWrongException;
import com.graduation.project.engine.core.securityConfig.JwtService;
import com.graduation.project.engine.user.model.Role;
import com.graduation.project.engine.user.model.User;
import com.graduation.project.engine.user.model.request.ChangePasswordRequestDto;
import com.graduation.project.engine.user.model.request.LoginRequestDto;
import com.graduation.project.engine.user.model.request.RegisterRequestDto;
import com.graduation.project.engine.user.model.request.UserUpdateRequestDto;
import com.graduation.project.engine.user.model.response.AuthenticationResponseDto;
import com.graduation.project.engine.user.repository.TokenRepository;
import com.graduation.project.engine.user.repository.UserRepository;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.mockito.InjectMocks;
import org.mockito.Mock;
import org.mockito.MockitoAnnotations;
import org.springframework.security.authentication.AuthenticationManager;

import java.time.LocalDateTime;
import java.util.Optional;

import static org.junit.jupiter.api.Assertions.*;
import static org.mockito.ArgumentMatchers.any;
import static org.mockito.Mockito.*;

import org.springframework.security.authentication.UsernamePasswordAuthenticationToken;
import org.springframework.security.core.AuthenticationException;
import org.springframework.security.crypto.password.PasswordEncoder;

public class UserServiceUnitTestImpl {

  @Mock
  private UserRepository userRepository;

  @Mock
  private PasswordEncoder passwordEncoder;

  @Mock
  private JwtService jwtService;

  @Mock
  private AuthenticationManager authenticationManager;

  @Mock
  private TokenRepository tokenRepository;

  @Mock
  private PasswordService passwordService;

  @InjectMocks
  private UserService authService;

  @BeforeEach
  void setUp() {
    MockitoAnnotations.openMocks(this);
  }

  @Test
  void register_Success() {
    // Arrange
    RegisterRequestDto request = new RegisterRequestDto("aziz", "can", "aziz@example.com",
        "password");
    User savedUser = User.builder()
        .firstName("aziz")
        .lastName("can")
        .email("aziz@example.com")
        .password("encodedPassword")
        .role(Role.ADMIN)
        .registeredAt(LocalDateTime.now())
        .build();

    when(userRepository.findByEmail(request.getEmail())).thenReturn(Optional.empty());
    when(passwordEncoder.encode(request.getPassword())).thenReturn("encodedPassword");
    when(userRepository.save(any(User.class))).thenReturn(savedUser);
    when(jwtService.generateToken(any(User.class))).thenReturn("jwtToken");

    // Act
    AuthenticationResponseDto response = authService.register(request);

    // Assert
    assertNotNull(response);
    assertEquals("jwtToken", response.getToken());
    assertEquals("aziz", response.getName());
    assertEquals("can", response.getLastName());
    assertEquals("aziz@example.com", response.getEmail());
    assertEquals(Role.ADMIN, response.getRole());

    verify(userRepository).findByEmail("aziz@example.com");
    verify(passwordEncoder).encode("password");
    verify(userRepository).save(any(User.class));
    verify(jwtService).generateToken(any(User.class));
    verify(tokenRepository).save(any());
  }

  @Test
  void register_EmailAlreadyExists_ThrowsException() {
    // Arrange
    RegisterRequestDto request = new RegisterRequestDto("aziz", "can", "aziz@example.com",
        "password");

    when(userRepository.findByEmail(request.getEmail())).thenReturn(Optional.of(new User()));

    // Act & Assert
    assertThrows(EntityAlreadyExistsException.class, () -> authService.register(request));

    verify(userRepository).findByEmail("aziz@example.com");
    verifyNoMoreInteractions(passwordEncoder, userRepository, jwtService, tokenRepository);
  }

  @Test
  void authenticate_ValidCredentials_ReturnsAuthenticationResponseDto() {
    // Arrange
    LoginRequestDto loginRequestDto = new LoginRequestDto();
    loginRequestDto.setEmail("aziz@example.com");
    loginRequestDto.setPassword("password");

    User user = User.builder()
        .id("1")
        .firstName("aziz")
        .lastName("can")
        .email("aziz@example.com")
        .password("hashedPassword")
        .build();

    when(userRepository.findByEmail(anyString())).thenReturn(java.util.Optional.of(user));
    when(jwtService.generateToken(any(User.class))).thenReturn("jwtToken");
    when(authenticationManager.authenticate(any(UsernamePasswordAuthenticationToken.class)))
        .thenReturn(null);

    // Act
    AuthenticationResponseDto responseDto = authService.authenticate(loginRequestDto);

    // Assert
    assertNotNull(responseDto);
    assertEquals("1", responseDto.getId());
    assertEquals("aziz", responseDto.getName());
    assertEquals("can", responseDto.getLastName());
    assertEquals("aziz@example.com", responseDto.getEmail());
    assertEquals("jwtToken", responseDto.getToken());
  }

  @Test
  void authenticate_InvalidCredentials_ThrowsPasswordWrongException() {
    // Arrange
    LoginRequestDto loginRequestDto = new LoginRequestDto();
    loginRequestDto.setEmail("aziz@example.com");
    loginRequestDto.setPassword("invalidPassword");

    when(authenticationManager.authenticate(any(UsernamePasswordAuthenticationToken.class)))
        .thenThrow(new AuthenticationException("Invalid credentials") {
        });

    // Act & Assert
    assertThrows(PasswordWrongException.class, () -> authService.authenticate(loginRequestDto));
  }

  @Test
  void testChangePassword_Success() throws Exception {
    // Arrange
    String userId = "user123";
    String newPassword = "newPassword123";
    String newPasswordConfirm = "newPassword123";

    User user = new User();
    user.setId(userId);
    user.setEmail("aziz@example.com");

    ChangePasswordRequestDto requestDto = new ChangePasswordRequestDto();
    requestDto.setSecretKey("encryptedSecretKey");
    requestDto.setPassword(newPassword);
    requestDto.setConfirmPassword(newPasswordConfirm);

    when(passwordService.decrypt(requestDto.getSecretKey())).thenReturn(user.getEmail());
    when(userRepository.findByEmail(user.getEmail())).thenReturn(Optional.of(user));
    when(passwordService.hashPassword(newPassword)).thenReturn("hashedPassword");
    when(passwordEncoder.encode(newPassword)).thenReturn("hashedPassword");
    when(userRepository.save(any())).thenReturn(user);

    // Act
    authService.changePassword(requestDto);

    // Assert
    verify(userRepository, times(1)).save(user);
  }

  @Test
  void testChangePassword_PasswordMismatch() throws Exception {
    // Arrange
    String newPassword = "newPassword123";
    String newPasswordConfirm = "wrongPassword123";
    String userEmail = "aziz@example.com";

    ChangePasswordRequestDto requestDto = new ChangePasswordRequestDto();
    requestDto.setSecretKey("encryptedSecretKey");
    requestDto.setPassword(newPassword);
    requestDto.setConfirmPassword(newPasswordConfirm);

    when(passwordService.decrypt(requestDto.getSecretKey())).thenReturn(userEmail);

    when(userRepository.findByEmail(userEmail)).thenReturn(Optional.empty());

    // Act and Assert
    assertThrows(EntityNotFoundException.class, () -> authService.changePassword(requestDto));

    // No interactions with userRepository.save() should occur
    verify(userRepository, never()).save(any());
  }

  @Test
  void testUpdateUser_Success() {
    // Arrange
    String userId = "user123";
    String newPassword = "newPassword123";
    String newPasswordConfirm = "newPassword123";

    UserUpdateRequestDto requestDto = UserUpdateRequestDto.builder()
        .newPassword(newPassword)
        .newPasswordConfirm(newPasswordConfirm)
        .build();

    User user = User.builder()
        .id(userId)
        .firstName("aziz")
        .lastName("can")
        .email("aziz@example.com")
        .password("hashedPassword")
        .role(Role.ADMIN)
        .build();

    when(userRepository.findById(userId)).thenReturn(Optional.of(user));
    when(passwordService.hashPassword(newPassword)).thenReturn("hashedNewPassword");

    // Act
    AuthenticationResponseDto responseDto = authService.updateUser(requestDto, userId);

    // Assert
    assertEquals(userId, responseDto.getId());
    assertEquals("aziz", responseDto.getName());
    assertEquals("can", responseDto.getLastName());
    assertEquals("aziz@example.com", responseDto.getEmail());
    assertEquals(Role.ADMIN, responseDto.getRole());

    verify(userRepository, times(1)).save(user);
  }

  @Test
  void testUpdateUser_PasswordMismatch() {
    // Arrange
    String userId = "user123";
    String newPassword = "newPassword123";
    String newPasswordConfirm = "wrongPassword123";

    UserUpdateRequestDto requestDto = UserUpdateRequestDto.builder()
        .newPassword(newPassword)
        .newPasswordConfirm(newPasswordConfirm)
        .build();

    User user = User.builder()
        .id(userId)
        .firstName("aziz")
        .lastName("can")
        .email("aziz@example.com")
        .password("hashedPassword")
        .role(Role.ADMIN)
        .build();

    when(userRepository.findById(userId)).thenReturn(Optional.of(user));

    // Act and Assert
    assertThrows(BadRequestException.class, () -> authService.updateUser(requestDto, userId));

    verify(userRepository, never()).save(any());
  }

  @Test
  void testUpdateUser_UserNotFound() {
    // Arrange
    String userId = "nonExistentUser";
    String newPassword = "newPassword123";
    String newPasswordConfirm = "newPassword123";

    UserUpdateRequestDto requestDto = UserUpdateRequestDto.builder()
        .newPassword(newPassword)
        .newPasswordConfirm(newPasswordConfirm)
        .build();

    when(userRepository.findById(userId)).thenReturn(Optional.empty());

    // Act and Assert
    assertThrows(EntityNotFoundException.class, () -> authService.updateUser(requestDto, userId));

    verify(userRepository, never()).save(any());
  }
}
