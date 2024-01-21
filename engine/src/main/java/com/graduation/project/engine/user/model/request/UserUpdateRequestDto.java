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
public class UserUpdateRequestDto {
  @NotBlank(message = "Password cannot be empty")
  private String newPassword;
  @NotBlank(message = "Password Confirm cannot be empty")
  private String newPasswordConfirm;
  @NotBlank(message = "Token cannot be empty")
  private String token;
}
