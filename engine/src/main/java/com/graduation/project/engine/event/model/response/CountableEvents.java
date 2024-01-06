package com.graduation.project.engine.event.model.response;

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
public class CountableEvents {

  private String id;
  private String date;
  private int fall;
  private int armsUp;
  private int frontBending;
}
