package com.graduation.project.engine.core.exception;

import static org.assertj.core.api.Assertions.assertThat;

import java.lang.reflect.Field;
import java.time.ZoneOffset;
import java.util.Arrays;
import java.util.Date;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import org.junit.jupiter.api.DisplayName;
import org.junit.jupiter.api.Test;
import org.springframework.core.MethodParameter;
import org.springframework.http.HttpHeaders;
import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.validation.BeanPropertyBindingResult;
import org.springframework.validation.BindingResult;
import org.springframework.web.bind.MethodArgumentNotValidException;

/**
 * Characterization tests for {@link GenericExceptionHandler}.
 *
 * <p>Pure unit test: every handler method returns a {@link ResponseEntity} directly, so no MVC
 * infrastructure is needed and nothing here depends on content negotiation.
 *
 * <p>This lives in the production package on purpose - {@code handleMethodArgumentNotValid} is
 * {@code protected}, and its body is exactly the sort of thing a Spring Boot upgrade changes
 * underneath you (Boot 3.2+ moved {@code ResponseEntityExceptionHandler} onto {@code ProblemDetail}
 * / RFC 7807 bodies; this override opts out of that, and the test proves it still does).
 */
class GenericExceptionHandlerTest {

  private final GenericExceptionHandler handler = new GenericExceptionHandler();

  @Test
  @DisplayName("EntityNotFoundException -> 404, error code 1, \"Entity Not Found.\"")
  void entityNotFound_maps404() {
    ResponseEntity<Object> response =
        handler.handleAException(new EntityNotFoundException("User Not Found: 42"));

    assertThat(response.getStatusCode()).isEqualTo(HttpStatus.NOT_FOUND);
    GenericExceptionSignature body = (GenericExceptionSignature) response.getBody();
    assertThat(body).isNotNull();
    assertThat(body.getMessage()).isEqualTo("User Not Found: 42");
    assertThat(body.getHttpStatus()).isEqualTo(HttpStatus.NOT_FOUND);
    assertThat(body.getErrorCode()).isEqualTo(1);
    assertThat(body.getErrorMessage()).isEqualTo("Entity Not Found.");
  }

  @Test
  @DisplayName("BadRequestException -> 400, error code 3, \"Bad Request.\"")
  void badRequest_maps400() {
    ResponseEntity<Object> response =
        handler.handleAException(new BadRequestException("nope"));

    assertThat(response.getStatusCode()).isEqualTo(HttpStatus.BAD_REQUEST);
    GenericExceptionSignature body = (GenericExceptionSignature) response.getBody();
    assertThat(body).isNotNull();
    assertThat(body.getMessage()).isEqualTo("nope");
    assertThat(body.getHttpStatus()).isEqualTo(HttpStatus.BAD_REQUEST);
    assertThat(body.getErrorCode()).isEqualTo(3);
    assertThat(body.getErrorMessage()).isEqualTo("Bad Request.");
  }

  @Test
  @DisplayName("EntityAlreadyExistsException -> 409 CONFLICT, error code 2 (the local var is misnamed badRequest)")
  void entityAlreadyExists_maps409() {
    ResponseEntity<Object> response =
        handler.handleAException(new EntityAlreadyExistsException("taken"));

    assertThat(response.getStatusCode()).isEqualTo(HttpStatus.CONFLICT);
    GenericExceptionSignature body = (GenericExceptionSignature) response.getBody();
    assertThat(body).isNotNull();
    assertThat(body.getHttpStatus()).isEqualTo(HttpStatus.CONFLICT);
    assertThat(body.getErrorCode()).isEqualTo(2);
    assertThat(body.getErrorMessage()).isEqualTo("Entity Already Exists.");
  }

  @Test
  @DisplayName("PasswordWrongException -> 401 UNAUTHORIZED, error code 5, \"Unauthorized.\"")
  void passwordWrong_maps401() {
    ResponseEntity<Object> response =
        handler.handleAException(new PasswordWrongException("User Password Not Match: a@b.com"));

    assertThat(response.getStatusCode()).isEqualTo(HttpStatus.UNAUTHORIZED);
    GenericExceptionSignature body = (GenericExceptionSignature) response.getBody();
    assertThat(body).isNotNull();
    assertThat(body.getMessage()).isEqualTo("User Password Not Match: a@b.com");
    assertThat(body.getHttpStatus()).isEqualTo(HttpStatus.UNAUTHORIZED);
    assertThat(body.getErrorCode()).isEqualTo(5);
    assertThat(body.getErrorMessage()).isEqualTo("Unauthorized.");
  }

  @Test
  @DisplayName("GenericExceptionSignature exposes exactly [message, httpStatus, timestamp, errorCode, errorMessage]")
  void signatureFieldNamesAreStable() {
    // These names ARE the JSON contract the React client reads. They are all final with no
    // @JsonProperty overrides, so renaming a field renames the wire field.
    List<String> fieldNames = Arrays.stream(GenericExceptionSignature.class.getDeclaredFields())
        .filter(f -> !f.isSynthetic())
        .map(Field::getName)
        .toList();

    assertThat(fieldNames)
        .containsExactly("message", "httpStatus", "timestamp", "errorCode", "errorMessage");
  }

  @Test
  @DisplayName("the timestamp is stamped in UTC (ZoneId.of(\"Z\")), not the JVM default zone")
  void timestampIsUtc() {
    ResponseEntity<Object> response = handler.handleAException(new BadRequestException("x"));

    GenericExceptionSignature body = (GenericExceptionSignature) response.getBody();
    assertThat(body).isNotNull();
    assertThat(body.getTimestamp().getZone().getRules())
        .isEqualTo(ZoneOffset.UTC.getRules());
  }

  @Test
  @DisplayName("bean-validation failures keep the legacy {timestamp,status,errors} body, NOT a ProblemDetail")
  void methodArgumentNotValid_keepsLegacyBodyShape() throws Exception {
    MethodArgumentNotValidException exception = methodArgumentNotValidWith(
        "email", "Email cannot be empty",
        "password", "Password cannot be empty");

    ResponseEntity<Object> response = handler.handleMethodArgumentNotValid(
        exception, new HttpHeaders(), HttpStatus.BAD_REQUEST, null);

    assertThat(response.getStatusCode()).isEqualTo(HttpStatus.BAD_REQUEST);

    @SuppressWarnings("unchecked")
    Map<String, Object> body = (Map<String, Object>) response.getBody();
    assertThat(body).isNotNull();
    assertThat(body).isInstanceOf(LinkedHashMap.class);
    assertThat(body.keySet()).containsExactly("timestamp", "status", "errors");
    assertThat(body.get("status")).isEqualTo(400);
    assertThat(body.get("timestamp")).isInstanceOf(Date.class);

    @SuppressWarnings("unchecked")
    Map<String, String> errors = (Map<String, String>) body.get("errors");
    assertThat(errors)
        .containsEntry("email", "Email cannot be empty")
        .containsEntry("password", "Password cannot be empty")
        .hasSize(2);
  }

  // -----------------------------------------------------------------------------------------

  /** Builds a real MethodArgumentNotValidException with the given field/message pairs. */
  private static MethodArgumentNotValidException methodArgumentNotValidWith(String... fieldsAndMessages)
      throws NoSuchMethodException {
    Credentials target = new Credentials();
    BindingResult bindingResult = new BeanPropertyBindingResult(target, "credentials");
    for (int i = 0; i < fieldsAndMessages.length; i += 2) {
      bindingResult.rejectValue(fieldsAndMessages[i], "NotBlank", fieldsAndMessages[i + 1]);
    }
    MethodParameter parameter = new MethodParameter(
        GenericExceptionHandlerTest.class.getDeclaredMethod("dummyEndpoint", Credentials.class), 0);
    return new MethodArgumentNotValidException(parameter, bindingResult);
  }

  @SuppressWarnings("unused")
  private void dummyEndpoint(Credentials credentials) {
    // Only ever used as a MethodParameter source.
  }

  /** Minimal bean so BeanPropertyBindingResult can resolve the rejected field names. */
  static class Credentials {

    private String email;
    private String password;

    public String getEmail() {
      return email;
    }

    public void setEmail(String email) {
      this.email = email;
    }

    public String getPassword() {
      return password;
    }

    public void setPassword(String password) {
      this.password = password;
    }
  }
}
