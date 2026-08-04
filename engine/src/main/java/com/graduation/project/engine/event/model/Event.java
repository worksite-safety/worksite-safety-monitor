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
    private BigDecimal confidencePercentage;
    private String eventType;
    private String isProcessed;
    private BigDecimal timePeriod;
    private Long startTime;
    private Long endTime;

    /**
     * Which unit {@link #timePeriod} is expressed in.
     *
     * <p>{@code null}/absent means version 1: {@code timePeriod} is in SECONDS, because that is
     * what the pre-rewrite detector sent and what every document written before this field existed
     * contains. {@link #SCHEMA_VERSION_MILLIS} means milliseconds.
     *
     * <p>Absence is the marker rather than an explicit {@code 1} on purpose. Spring Data MongoDB
     * does not write null properties, so every legacy document already carries the "version 1"
     * signal without being touched, and the migration's filter - {@code schemaVersion} absent -
     * is therefore idempotent by construction rather than by a flag someone has to remember to
     * set. Re-running the migration selects nothing the second time.
     */
    private Integer schemaVersion;

    /** {@link #timePeriod} is in milliseconds. */
    public static final int SCHEMA_VERSION_MILLIS = 2;
}
