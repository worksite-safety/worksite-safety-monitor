package com.graduation.project.engine.rawEvent.model;

import com.fasterxml.jackson.annotation.JsonIgnoreProperties;
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
@JsonIgnoreProperties(ignoreUnknown = true)
public class RawEvent {

    private String cameraName;
    private String confidencePercentage;
    private String eventType;
    private String isProcessed;
    private BigDecimal timePeriod;
    private Long startTime;
    private Long endTime;
}
