package com.graduation.project.engine.models;

import lombok.AllArgsConstructor;
import lombok.Builder;
import lombok.Data;
import lombok.NoArgsConstructor;

@Data
@Builder
@NoArgsConstructor
@AllArgsConstructor
public class DefaultStats {

    private Integer totalDetectedFall;
    private Double averageConfidenceRate;
    private Double averageDailyEnergyExpenditureRate;

}
