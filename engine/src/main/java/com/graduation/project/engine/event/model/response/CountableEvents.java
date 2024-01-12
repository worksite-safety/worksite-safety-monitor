package com.graduation.project.engine.event.model.response;

import lombok.AllArgsConstructor;
import lombok.Builder;
import lombok.Data;
import lombok.NoArgsConstructor;

@Data
@Builder
@NoArgsConstructor
@AllArgsConstructor
public class CountableEvents {

  private String date;
  private int fall;
  private int armsUp;
  private int frontBending;
}
