package com.graduation.project.engine.event.model;

import lombok.AllArgsConstructor;
import lombok.Builder;
import lombok.Data;
import lombok.NoArgsConstructor;

@Data
@Builder
@NoArgsConstructor
@AllArgsConstructor
public class SummaryStats {

    private Integer totalDetectedFall;
    private Double averageConfidenceRate;
    private Double averageDailyEnergyExpenditureRate;

}
