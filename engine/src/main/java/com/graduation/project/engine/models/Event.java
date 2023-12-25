package com.graduation.project.engine.models;

import lombok.AllArgsConstructor;
import lombok.Builder;
import lombok.Data;
import lombok.NoArgsConstructor;
import org.springframework.data.annotation.Id;
import org.springframework.data.mongodb.core.mapping.Document;

import java.util.List;

@Data
@Builder
@NoArgsConstructor
@AllArgsConstructor
@Document("event")
public class Event {
    @Id
    private String id;
    private String eventPrediction;
    private String timestamp;
    private Double confidenceRate;
}
