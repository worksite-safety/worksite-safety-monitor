package com.graduation.project.engine.models;

import lombok.AllArgsConstructor;
import lombok.Builder;
import lombok.Data;
import lombok.NoArgsConstructor;
import org.springframework.data.annotation.Id;
import org.springframework.data.mongodb.core.mapping.Document;
import org.springframework.data.mongodb.core.mapping.Field;

import java.math.BigDecimal;

@Data
@Builder
@NoArgsConstructor
@AllArgsConstructor
@Document("rawEvent")
public class RawEvent {

    @Id
    private String id;
    private String cameraName;
    private String confidencePercentage;
    private String eventPrediction;
    private String isProcessed;
    private BigDecimal timePeriod;
    private Long startTime;
    private Long endTime;
}
