package com.graduation.project.engine.core.exception;

public enum ErrorCode {

    ENTITY_NOT_FOUND(1, "Entity Not Found."),
    ENTITY_ALREADY_EXISTS(2, "Entity Already Exists."),
    BAD_REQUEST(3, "Bad Request."),
    INTERNAL_SERVER_ERROR(4, "Internal Server Error."),
    UNAUTHORIZED(5, "Unauthorized.");


    private final int code;
    private final String message;

    ErrorCode(int code, String message) {
        this.code = code;
        this.message = message;
    }
    public int getCode() {
        return code;
    }
    public String getMessage() {
        return message;
    }


}
