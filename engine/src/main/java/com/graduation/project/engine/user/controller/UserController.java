package com.graduation.project.engine.user.controller;

import com.graduation.project.engine.user.model.request.LoginRequestDto;
import com.graduation.project.engine.user.model.request.RegisterRequestDto;
import com.graduation.project.engine.user.model.response.AuthenticationResponseDto;
import com.graduation.project.engine.user.service.UserService;
import jakarta.validation.Valid;
import lombok.RequiredArgsConstructor;
import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.*;

@RestController
@RequestMapping("/auth")
@RequiredArgsConstructor
@CrossOrigin
public class UserController {

    private final UserService userService;

    @PostMapping("/register")
    public ResponseEntity<AuthenticationResponseDto> register(@Valid @RequestBody RegisterRequestDto request) {
        return new ResponseEntity<>(userService.register(request), HttpStatus.CREATED);
    }
    @PostMapping("/login")
    public ResponseEntity<AuthenticationResponseDto> login(@RequestBody LoginRequestDto request) {
        return ResponseEntity.ok(userService.authenticate(request));
    }
}
