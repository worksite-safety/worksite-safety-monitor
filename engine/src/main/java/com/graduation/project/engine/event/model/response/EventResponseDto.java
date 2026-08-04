package com.graduation.project.engine.event.model.response;

import com.graduation.project.engine.event.model.Event;
import java.math.BigDecimal;
import lombok.AllArgsConstructor;
import lombok.Builder;
import lombok.Data;
import lombok.NoArgsConstructor;

/**
 * The wire shape of {@code GET /event/all-events}.
 *
 * <h2>Why a DTO, when the endpoint used to return {@link Event} straight from the repository</h2>
 *
 * <p><b>1. The unit.</b> {@code Event.timePeriod} is MILLISECONDS in storage; the API is SECONDS
 * everywhere else ({@code /event/periodic-events} converts, and has a long comment saying why).
 * Returning the entity meant this one endpoint contradicted the rest of the API, and
 * {@code web/src/pages/Reporting.js} rendered the raw field in a column headed "Time Period" -
 * every duration a thousand times too large, with nothing in a log to say so. Something has to
 * convert. The candidates were: change the entity (no - it would corrupt
 * {@code PeriodicTimePeriodMigration}, {@code RawEventService} and the repository round trip, all
 * of which mean milliseconds); change the frontend (out of scope, and it would leave the API
 * self-contradictory for any other client); or convert at the boundary, which is what the periodic
 * chart already does. A DTO is where "the boundary" is expressible.
 *
 * <p><b>2. {@code schemaVersion} must not travel.</b> That field records WHICH UNIT the stored
 * value is in. Once this DTO has normalised the value to seconds the field is not merely
 * redundant, it is false: a payload reading {@code {"timePeriod": 5, "schemaVersion": 2}} states
 * that 5 is milliseconds. A storage-versioning marker leaking into a public payload is the same
 * class of mistake as the unit bug itself.
 *
 * <p><b>3. It stops the document shape from being the API.</b> Serialising the entity means any
 * change to storage is an unannounced change to the contract - and one is already scheduled:
 * {@code EventRepositoryIT} pins that {@code BigDecimal} persists as a BSON String today and
 * records that Spring Data MongoDB 4.2+ moves towards Decimal128 during the Boot 3.5.x upgrade.
 *
 * <h2>What is deliberately NOT here</h2>
 *
 * <ul>
 *   <li>{@code schemaVersion} - see above.</li>
 *   <li>{@code isProcessed} - an ingest-side flag, written verbatim from the detector payload and
 *       read by nothing in this application or in {@code web/}.</li>
 * </ul>
 *
 * <p>Everything the events grid binds - {@code id}, {@code eventType}, {@code startTime},
 * {@code confidencePercentage}, {@code timePeriod}, {@code cameraName} - keeps its exact name, so
 * {@code web/} needs no change. {@code endTime} is kept because it is real event data that was in
 * the payload before.
 */
@Data
@Builder
@NoArgsConstructor
@AllArgsConstructor
public class EventResponseDto {

  private String id;
  private String cameraName;
  private BigDecimal confidencePercentage;
  private String eventType;
  private Long startTime;
  private Long endTime;

  /**
   * The violation's duration in WHOLE SECONDS, or {@code null} for event types that have no
   * duration (FALL, ARMS_UP, FRONT_BEND).
   *
   * <p>{@code Integer} and nullable rather than a primitive, and NOT annotated
   * {@code @JsonInclude(NON_NULL)}. The grid renders {@code row.timePeriod === null ? '-' : ...},
   * which is a strict comparison: a countable event must arrive as an explicit JSON
   * {@code null}. Omitting the key would make it {@code undefined}, fail the {@code === null}
   * test and print "undefined" in the cell; defaulting it to {@code 0} would claim a zero-second
   * violation for an event that never had a duration at all.
   */
  private Integer timePeriod;
}
