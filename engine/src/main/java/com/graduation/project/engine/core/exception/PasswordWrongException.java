package com.graduation.project.engine.core.exception;

import org.springframework.http.HttpStatus;
import org.springframework.web.bind.annotation.ResponseStatus;

@ResponseStatus(HttpStatus.UNAUTHORIZED)
public class PasswordWrongException extends RuntimeException {

  public PasswordWrongException(String message) {
    super(message);
  }

}
