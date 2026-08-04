package com.graduation.project.engine.rawEvent.service;

import com.graduation.project.engine.email.service.MailService;
import com.graduation.project.engine.event.model.Event;
import com.graduation.project.engine.event.model.EventNameEnum;
import com.graduation.project.engine.event.repository.EventRepository;
import com.graduation.project.engine.rawEvent.model.PeriodicInputUnit;
import com.graduation.project.engine.rawEvent.model.RawEvent;
import com.graduation.project.engine.user.model.User;
import com.graduation.project.engine.user.model.converter.UserResponseDto2UserConverter;
import com.graduation.project.engine.user.service.UserService;
import java.math.BigDecimal;
import java.time.LocalDateTime;
import java.util.List;
import lombok.RequiredArgsConstructor;
import lombok.SneakyThrows;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.kafka.annotation.KafkaListener;
import org.springframework.stereotype.Service;

@Service
@RequiredArgsConstructor
public class RawEventService {

  private final EventRepository eventRepository;
  private final MailService mailService;
  private final UserService userService;
  private final UserResponseDto2UserConverter userResponseDto2UserConverter;

  /**
   * The shortest periodic violation worth storing, in milliseconds.
   *
   * <p>Replaces {@code event.fall.threshold.value}. The old name was wrong twice over: it named
   * FALL while it only ever gated NO_HELMET/NO_JACKET, and it carried no unit, which is how a
   * value meaning "3 seconds" survived the detector switching to milliseconds and started
   * admitting 33 ms flickers. {@code long}, not {@code int}: see {@link #listener}.
   */
  @Value("${event.periodic.min-duration-ms}")
  private long minPeriodicDurationMs;

  /**
   * The unit the detector currently sends {@code timePeriod} in. Defaults to {@code SECONDS},
   * which describes the producer in the field before the rewrite ships; flip it to {@code MILLIS}
   * as part of the detector release.
   */
  @Value("${event.periodic.input-unit:SECONDS}")
  private PeriodicInputUnit periodicInputUnit;

  Logger logger = LoggerFactory.getLogger(RawEventService.class);

  @KafkaListener(topics = "${kafka.raw-event.topic}", groupId = "${kafka.raw-event.group-id}")
  @SneakyThrows
  void listener(RawEvent data) {
    logger.info("Listener received: {} !", data);

    // RawEvent is @JsonIgnoreProperties(ignoreUnknown = true) and has no required fields, so a
    // payload that simply omits eventType deserialises cleanly and every branch below throws
    // NullPointerException on its first .equals(...). Thrown, that exception reaches the
    // container's error handler, which re-invokes this method for the same record - ten times
    // with spring-kafka's default backoff - before giving up. An event with no type can never
    // be routed, so it is dropped here, once, where the reason can still be logged.
    if (data == null || data.getEventType() == null) {
      logger.warn("Dropping raw event with no eventType: {}", data);
      return;
    }

    if (data.getEventType().equals(EventNameEnum.FALL.name())) {
      List<User> users = userResponseDto2UserConverter.convert(userService.getAllUsers());
      for (User user : users) {
        logger.warn("Sending mail to: " + user.getEmail());
        mailService.sendUrgentEventMail(user, LocalDateTime.now(), data.getCameraName());
      }
    }

    if (data.getEventType().equals(EventNameEnum.NO_HELMET.name()) || data.getEventType()
        .equals(EventNameEnum.NO_JACKET.name())) {
      // Normalise BEFORE comparing, and store what was compared. Everything downstream of this
      // line - the threshold, the collection, the migration, the chart - is in milliseconds; the
      // producer's unit is a fact about the wire and dies here.
      BigDecimal timePeriodMillis = periodicInputUnit.toMillis(data.getTimePeriod());

      // longValue(), not intValue(). BigDecimal.intValue() returns the low-order 32 bits without
      // throwing when the value does not fit, so a window longer than ~24.8 days wraps to a
      // negative int and silently fails the check - discarding precisely the longest, most
      // serious violations. A stuck camera reaches that in under a month.
      if (timePeriodMillis.longValue() > minPeriodicDurationMs) {
        eventRepository.save(Event.builder()
            .eventType(data.getEventType())
            .startTime(data.getStartTime())
            .confidencePercentage(data.getConfidencePercentage())
            .cameraName(data.getCameraName())
            .timePeriod(timePeriodMillis)
            .isProcessed(data.getIsProcessed())
            // Stamped because the value above is already normalised. PeriodicTimePeriodMigration
            // selects periodic documents whose schemaVersion is ABSENT; without this stamp a
            // migration run after this engine ships would multiply these by 1000 a second time.
            // Only this branch is stamped: the else branch stores timePeriod verbatim, so
            // claiming a unit for it would be a lie.
            .schemaVersion(Event.SCHEMA_VERSION_MILLIS)
            .build());
      }
    } else {
      eventRepository.save(Event.builder()
          .eventType(data.getEventType())
          .startTime(data.getStartTime())
          .confidencePercentage(data.getConfidencePercentage())
          .cameraName(data.getCameraName())
          .timePeriod(data.getTimePeriod())
          .isProcessed(data.getIsProcessed())
          .build());
    }
  }
}
