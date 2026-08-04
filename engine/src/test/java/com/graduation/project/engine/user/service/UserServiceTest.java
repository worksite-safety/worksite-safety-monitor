package com.graduation.project.engine.user.service;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertNotNull;
import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.mockito.ArgumentMatchers.any;
import static org.mockito.ArgumentMatchers.anyString;
import static org.mockito.Mockito.never;
import static org.mockito.Mockito.times;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.verifyNoMoreInteractions;
import static org.mockito.Mockito.when;

import com.graduation.project.engine.core.PasswordService;
import com.graduation.project.engine.core.exception.BadRequestException;
import com.graduation.project.engine.core.exception.EntityAlreadyExistsException;
import com.graduation.project.engine.core.exception.EntityNotFoundException;
import com.graduation.project.engine.core.exception.PasswordWrongException;
import com.graduation.project.engine.core.securityConfig.JwtService;
import com.graduation.project.engine.email.service.MailService;
import com.graduation.project.engine.user.model.Role;
import com.graduation.project.engine.user.model.User;
import com.graduation.project.engine.user.model.converter.User2UserResponseDtoConverter;
import com.graduation.project.engine.user.model.request.ChangePasswordRequestDto;
import com.graduation.project.engine.user.model.request.LoginRequestDto;
import com.graduation.project.engine.user.model.request.RegisterRequestDto;
import com.graduation.project.engine.user.model.request.UserUpdateRequestDto;
import com.graduation.project.engine.user.model.response.AuthenticationResponseDto;
import com.graduation.project.engine.user.repository.TokenRepository;
import com.graduation.project.engine.user.repository.UserRepository;
import java.time.LocalDateTime;
import java.util.Optional;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.extension.ExtendWith;
import org.mockito.InjectMocks;
import org.mockito.Mock;
import org.mockito.junit.jupiter.MockitoExtension;
import org.springframework.security.authentication.AuthenticationManager;
import org.springframework.security.authentication.UsernamePasswordAuthenticationToken;
import org.springframework.security.core.AuthenticationException;
import org.springframework.security.crypto.password.PasswordEncoder;

/**
 * Unit tests for {@link UserService}.
 *
 * <p>MockitoExtension replaces the old {@code MockitoAnnotations.openMocks(this)} in
 * {@code @BeforeEach} - the returned AutoCloseable was never closed. It also enables
 * STRICT_STUBS, so every {@code when(...)} here must actually be exercised.
 */
@ExtendWith(MockitoExtension.class)
class UserServiceTest {

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
  private User2UserResponseDtoConverter user2UserResponseDtoConverter;

  @Mock
  private PasswordService passwordService;

  @Mock
  private MailService mailService;

  @InjectMocks
  private UserService authService;

  @Test
  void register_Success() {
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

    AuthenticationResponseDto response = authService.register(request);

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
    RegisterRequestDto request = new RegisterRequestDto("aziz", "can", "aziz@example.com",
        "password");

    when(userRepository.findByEmail(request.getEmail())).thenReturn(Optional.of(new User()));

    assertThrows(EntityAlreadyExistsException.class, () -> authService.register(request));

    verify(userRepository).findByEmail("aziz@example.com");
    verifyNoMoreInteractions(passwordEncoder, userRepository, jwtService, tokenRepository);
  }

  @Test
  void authenticate_ValidCredentials_ReturnsAuthenticationResponseDto() {
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

    when(userRepository.findByEmail(anyString())).thenReturn(Optional.of(user));
    when(jwtService.generateToken(any(User.class))).thenReturn("jwtToken");
    when(authenticationManager.authenticate(any(UsernamePasswordAuthenticationToken.class)))
        .thenReturn(null);

    AuthenticationResponseDto responseDto = authService.authenticate(loginRequestDto);

    assertNotNull(responseDto);
    assertEquals("1", responseDto.getId());
    assertEquals("aziz", responseDto.getName());
    assertEquals("can", responseDto.getLastName());
    assertEquals("aziz@example.com", responseDto.getEmail());
    assertEquals("jwtToken", responseDto.getToken());
  }

  @Test
  void authenticate_InvalidCredentials_ThrowsPasswordWrongException() {
    LoginRequestDto loginRequestDto = new LoginRequestDto();
    loginRequestDto.setEmail("aziz@example.com");
    loginRequestDto.setPassword("invalidPassword");

    User user = User.builder()
        .id("1")
        .firstName("aziz")
        .lastName("can")
        .email("aziz@example.com")
        .password("hashedPassword")
        .build();

    // Without this stub UserService.authenticate throws EntityNotFoundException on the
    // repository lookup and never reaches the AuthenticationManager, so the test would
    // pass for the wrong reason (it would not, in fact - it asserts PasswordWrongException).
    when(userRepository.findByEmail("aziz@example.com")).thenReturn(Optional.of(user));
    when(authenticationManager.authenticate(any(UsernamePasswordAuthenticationToken.class)))
        .thenThrow(new AuthenticationException("Invalid credentials") {
        });

    assertThrows(PasswordWrongException.class, () -> authService.authenticate(loginRequestDto));

    verify(jwtService, never()).generateToken(any(User.class));
  }

  @Test
  void testChangePassword_Success() throws Exception {
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
    // UserService.changePassword hashes via PasswordService, NOT PasswordEncoder - the old
    // passwordEncoder.encode(...) stub here was never used (UnnecessaryStubbingException).
    when(passwordService.hashPassword(newPassword)).thenReturn("hashedPassword");
    when(userRepository.save(any())).thenReturn(user);

    authService.changePassword(requestDto);

    assertEquals("hashedPassword", user.getPassword());
    verify(userRepository, times(1)).save(user);
  }

  @Test
  void testChangePassword_PasswordMismatch() throws Exception {
    String newPassword = "newPassword123";
    String newPasswordConfirm = "wrongPassword123";
    String userEmail = "aziz@example.com";

    ChangePasswordRequestDto requestDto = new ChangePasswordRequestDto();
    requestDto.setSecretKey("encryptedSecretKey");
    requestDto.setPassword(newPassword);
    requestDto.setConfirmPassword(newPasswordConfirm);

    when(passwordService.decrypt(requestDto.getSecretKey())).thenReturn(userEmail);
    when(userRepository.findByEmail(userEmail)).thenReturn(Optional.empty());

    // Characterization: the unknown-user lookup fails before the mismatch check runs, so
    // this asserts EntityNotFoundException despite the method name.
    assertThrows(EntityNotFoundException.class, () -> authService.changePassword(requestDto));

    verify(userRepository, never()).save(any());
  }

  @Test
  void testUpdateUser_Success() {
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

    AuthenticationResponseDto responseDto = authService.updateUser(requestDto, userId);

    assertEquals(userId, responseDto.getId());
    assertEquals("aziz", responseDto.getName());
    assertEquals("can", responseDto.getLastName());
    assertEquals("aziz@example.com", responseDto.getEmail());
    assertEquals(Role.ADMIN, responseDto.getRole());

    verify(userRepository, times(1)).save(user);
  }

  @Test
  void testUpdateUser_PasswordMismatch() {
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

    assertThrows(BadRequestException.class, () -> authService.updateUser(requestDto, userId));

    verify(userRepository, never()).save(any());
  }

  @Test
  void testUpdateUser_UserNotFound() {
    String userId = "nonExistentUser";
    String newPassword = "newPassword123";
    String newPasswordConfirm = "newPassword123";

    UserUpdateRequestDto requestDto = UserUpdateRequestDto.builder()
        .newPassword(newPassword)
        .newPasswordConfirm(newPasswordConfirm)
        .build();

    when(userRepository.findById(userId)).thenReturn(Optional.empty());

    assertThrows(EntityNotFoundException.class, () -> authService.updateUser(requestDto, userId));

    verify(userRepository, never()).save(any());
  }
}
