package com.graduation.project.engine.models;

import lombok.Data;
import org.springframework.data.annotation.Id;
import org.springframework.data.mongodb.core.mapping.Document;

@Document("testitems")
@Data
public class TestDoc {

    @Id
    private String id;

    private String name;
    private int quantity;
    private String category;
    public TestDoc(String id, String name, int quantity, String category) {
        super();
        this.id = id;
        this.name = name;
        this.quantity = quantity;
        this.category = category;

    }
}
