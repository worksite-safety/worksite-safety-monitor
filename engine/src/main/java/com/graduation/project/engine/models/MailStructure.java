package com.graduation.project.engine.models;

import lombok.Getter;
import lombok.Setter;

@Getter
@Setter
public class MailStructure {

    private String subject;
    private String message;

    public String getMessage() {
        return this.message;
    }
}
