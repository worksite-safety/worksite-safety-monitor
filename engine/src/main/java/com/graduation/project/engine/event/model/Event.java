package com.graduation.project.engine.event.model;

import java.math.BigDecimal;
import lombok.AllArgsConstructor;
import lombok.Builder;
import lombok.Data;
import lombok.NoArgsConstructor;
import org.springframework.data.annotation.Id;
import org.springframework.data.mongodb.core.mapping.Document;

@Data
@Builder
@NoArgsConstructor
@AllArgsConstructor
@Document("event")
public class Event {
    @Id
    private String id;
    private String cameraName;
    private String confidencePercentage;
    private String eventType;
    private String isProcessed;
    private BigDecimal timePeriod;
    private Long startTime;
    private Long endTime;
}
