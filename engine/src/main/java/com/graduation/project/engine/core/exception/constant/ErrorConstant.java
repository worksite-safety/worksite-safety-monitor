package com.graduation.project.engine.core.exception.constant;

public class ErrorConstant {


    public static final String USER_NOT_FOUND_MESSAGE = "User Not Found: ";
    public static final String USER_ALREADY_EXISTS_MESSAGE = "User Already Exists: ";
    public static final String USER_EMAIL_ALREADY_EXISTS = "User Email Already Exists: ";
    public static final String USER_PASSWORD_NOT_MATCH = "User Password Not Match: ";
    public static String errorMessageParser(String message, int data){
        return String.format("%s%d", message, data);
    }
    public static String errorMessageParser(String message, String data){
        return String.format("%s%s", message, data);
    }
}
