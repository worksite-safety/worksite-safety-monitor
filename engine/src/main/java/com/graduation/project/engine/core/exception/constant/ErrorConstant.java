package com.graduation.project.engine.core.exception.constant;

public class ErrorConstant {


    public static final String USER_NOT_FOUND_MESSAGE = "User Not Found: ";
    /**
     * For lookups of an {@code Event} by id. Separate from {@link #USER_NOT_FOUND_MESSAGE}
     * because {@code EventService.deletePeriodicEventById} used to reuse that one, and answered a
     * failed event delete with "User Not Found: &lt;eventId&gt;" - the wrong entity name next to an
     * event id, which points whoever reads it at the wrong collection.
     */
    public static final String EVENT_NOT_FOUND_MESSAGE = "Event Not Found: ";
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
