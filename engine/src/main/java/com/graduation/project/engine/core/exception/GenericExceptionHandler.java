package com.graduation.project.engine.core.exception;

import org.springframework.http.HttpHeaders;
import org.springframework.http.HttpStatus;
import org.springframework.http.HttpStatusCode;
import org.springframework.http.ResponseEntity;
import org.springframework.validation.FieldError;
import org.springframework.web.bind.MethodArgumentNotValidException;
import org.springframework.web.bind.annotation.ControllerAdvice;
import org.springframework.web.bind.annotation.ExceptionHandler;
import org.springframework.web.context.request.WebRequest;
import org.springframework.web.servlet.mvc.method.annotation.ResponseEntityExceptionHandler;

import java.time.ZoneId;
import java.time.ZonedDateTime;
import java.util.*;

@ControllerAdvice
public class GenericExceptionHandler extends ResponseEntityExceptionHandler {

    @ExceptionHandler(value = {EntityNotFoundException.class})
    public ResponseEntity<Object> handleAException(EntityNotFoundException e) {
        HttpStatus notFound = HttpStatus.NOT_FOUND;
        GenericExceptionSignature notFoundException = new GenericExceptionSignature(e.getMessage(), notFound, ZonedDateTime.now(ZoneId.of("Z")), ErrorCode.ENTITY_NOT_FOUND.getCode(), ErrorCode.ENTITY_NOT_FOUND.getMessage());
        return new ResponseEntity<>(notFoundException, notFound);
    }

    @ExceptionHandler(value = {BadRequestException.class})
    public ResponseEntity<Object> handleAException(BadRequestException e) {
        HttpStatus badRequest = HttpStatus.BAD_REQUEST;
        GenericExceptionSignature badRequestException = new GenericExceptionSignature(e.getMessage(), badRequest, ZonedDateTime.now(ZoneId.of("Z")), ErrorCode.BAD_REQUEST.getCode(), ErrorCode.BAD_REQUEST.getMessage());
        return new ResponseEntity<>(badRequestException, badRequest);
    }

    @ExceptionHandler(value = {EntityAlreadyExistsException.class})
    public ResponseEntity<Object> handleAException(EntityAlreadyExistsException e) {
        HttpStatus badRequest = HttpStatus.CONFLICT;
        GenericExceptionSignature entityAlreadyExistsException = new GenericExceptionSignature(e.getMessage(), badRequest, ZonedDateTime.now(ZoneId.of("Z")), ErrorCode.ENTITY_ALREADY_EXISTS.getCode(), ErrorCode.ENTITY_ALREADY_EXISTS.getMessage());
        return new ResponseEntity<>(entityAlreadyExistsException, badRequest);
    }
    @ExceptionHandler(value = {PasswordWrongException.class})
    public ResponseEntity<Object> handleAException(PasswordWrongException e) {
        HttpStatus badRequest = HttpStatus.UNAUTHORIZED;
        GenericExceptionSignature entityAlreadyExistsException = new GenericExceptionSignature(e.getMessage(), badRequest, ZonedDateTime.now(ZoneId.of("Z")), ErrorCode.UNAUTHORIZED.getCode(), ErrorCode.UNAUTHORIZED.getMessage());
        return new ResponseEntity<>(entityAlreadyExistsException, badRequest);
    }


    @Override
    protected ResponseEntity<Object> handleMethodArgumentNotValid(MethodArgumentNotValidException ex, HttpHeaders headers, HttpStatusCode status, WebRequest request) {
        Map<String, Object> responseBody = new LinkedHashMap<>();
        responseBody.put("timestamp", new Date());
        responseBody.put("status", status.value());
        List<FieldError> fieldErrorList = ex.getBindingResult().getFieldErrors();

        Map<String, String> errorFieldMessageMap = new HashMap<>();
        fieldErrorList.forEach((f) -> errorFieldMessageMap.put(f.getField(), f.getDefaultMessage()));
        responseBody.put("errors", errorFieldMessageMap);
        return new ResponseEntity<>(responseBody, headers, status);
    }
}
