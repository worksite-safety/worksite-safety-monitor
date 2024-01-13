package com.graduation.project.engine.event.model.response;

import lombok.AllArgsConstructor;
import lombok.Builder;
import lombok.Data;
import lombok.NoArgsConstructor;

@Data
@Builder
@NoArgsConstructor
@AllArgsConstructor
public class PeriodicEvents {

  private String date;
  private int noHelmet;
  private int noJacket;
}
