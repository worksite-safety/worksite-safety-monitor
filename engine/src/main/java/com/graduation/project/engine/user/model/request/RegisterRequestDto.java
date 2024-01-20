package com.graduation.project.engine.user.model.request;

import jakarta.validation.constraints.NotBlank;
import lombok.AllArgsConstructor;
import lombok.Builder;
import lombok.Data;
import lombok.NoArgsConstructor;

@Data
@AllArgsConstructor
@NoArgsConstructor
@Builder
public class RegisterRequestDto {

  @NotBlank(message = "First Name cannot be empty")
  private String firstName;
  @NotBlank(message = "Last Name cannot be empty")
  private String lastName;
  @NotBlank(message = "Email cannot be empty")
  private String email;
  @NotBlank(message = "Password cannot be empty")
  private String password;
}