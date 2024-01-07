package com.graduation.project.engine.user.model.request;

import lombok.AllArgsConstructor;
import lombok.Builder;
import lombok.Data;
import lombok.NoArgsConstructor;

@Data
@AllArgsConstructor
@NoArgsConstructor
@Builder
public class ChangePasswordRequestDto {
  private String secretKey;
  private String password;
  private String confirmPassword;
}
