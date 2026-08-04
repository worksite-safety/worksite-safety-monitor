package com.graduation.project.engine.user.controller;

import com.graduation.project.engine.user.model.request.ChangePasswordRequestDto;
import com.graduation.project.engine.user.model.request.ForgotPasswordRequestDto;
import com.graduation.project.engine.user.model.request.LoginRequestDto;
import com.graduation.project.engine.user.model.request.RegisterRequestDto;
import com.graduation.project.engine.user.model.request.UserUpdateRequestDto;
import com.graduation.project.engine.user.model.response.AuthenticationResponseDto;
import com.graduation.project.engine.user.service.UserService;
import io.swagger.v3.oas.annotations.Operation;
import io.swagger.v3.oas.annotations.security.SecurityRequirement;
import jakarta.validation.Valid;
import lombok.RequiredArgsConstructor;
import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.*;

// No @CrossOrigin - see the note on EventController and
// SecurityConfiguration#corsConfigurationSource. It mattered more here than anywhere: a bare
// @CrossOrigin on the /auth endpoints let any origin drive login, registration and password reset.
@RestController
@RequestMapping("/auth")
@RequiredArgsConstructor
public class UserController {

  private final UserService userService;

  @PostMapping("/register")
  public ResponseEntity<AuthenticationResponseDto> register(
      @Valid @RequestBody RegisterRequestDto request) {
    return new ResponseEntity<>(userService.register(request), HttpStatus.CREATED);
  }

  @PostMapping("/login")
  public ResponseEntity<AuthenticationResponseDto> login(@RequestBody LoginRequestDto request) {
    return ResponseEntity.ok(userService.authenticate(request));
  }

  @PostMapping("/forgot-password")
  public ResponseEntity<?> forgotPassword(@RequestBody ForgotPasswordRequestDto request) {

    userService.forgotPassword(request.getEmail());
    return ResponseEntity.ok("Successfully mail sent !!");

  }

  @PostMapping("/change-password")
  public ResponseEntity<?> changePassword(@RequestBody ChangePasswordRequestDto request) {

    userService.changePassword(request);
    return ResponseEntity.ok("");

  }

  @PutMapping("/update-user/{userId}")
  @Operation(description = "Update User Password", summary = "Update User", security = @SecurityRequirement(name = "bearerAuth"))
  public ResponseEntity<AuthenticationResponseDto> update(@RequestBody UserUpdateRequestDto request,
      @PathVariable("userId") String userId) {
    return ResponseEntity.ok(userService.updateUser(request, userId));
  }
}
