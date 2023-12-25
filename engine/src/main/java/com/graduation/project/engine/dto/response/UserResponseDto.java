package com.graduation.project.engine.dto.response;

import com.graduation.project.engine.models.Role;
import lombok.AllArgsConstructor;
import lombok.Builder;
import lombok.Data;
import lombok.NoArgsConstructor;

import java.time.LocalDateTime;

@Data
@AllArgsConstructor
@NoArgsConstructor
@Builder
public class UserResponseDto {
    private String userId;
    private String email;
    private String firstName;
    private String lastName;
    private Role role;
    private Boolean isEnabled;
}