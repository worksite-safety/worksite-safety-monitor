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
import java.util.Arrays;
import java.util.List;
import java.util.Set;
import java.util.stream.Collectors;
import lombok.RequiredArgsConstructor;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.kafka.annotation.KafkaListener;
import org.springframework.stereotype.Service;

@Service
@RequiredArgsConstructor
public class RawEventService {

  /**
   * The complete set of event types this backend can route, derived from {@link EventNameEnum}
   * rather than restated, so that adding an enum constant is enough to make it acceptable on the
   * topic and there is no second list to forget.
   */
  private static final Set<String> KNOWN_EVENT_TYPES = Arrays.stream(EventNameEnum.values())
      .map(Enum::name)
      .collect(Collectors.toUnmodifiableSet());

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

  // @SneakyThrows removed with the mail try/catch below: nothing in this method throws a checked
  // exception any more. It was doing real damage here - it existed only to swallow the compiler's
  // complaint about MessagingException, and in doing so it made "a mail send can abort this
  // listener and hand the record back to the container" invisible at the signature.
  @KafkaListener(topics = "${kafka.raw-event.topic}", groupId = "${kafka.raw-event.group-id}")
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

    // Reject-by-default, for the same reason and in the same shape as the null check above.
    //
    // Nothing validated eventType against EventNameEnum, so any string the detector produced -
    // a renamed class, a typo, a model from a different project - fell through to the else
    // branch and was written to the "event" collection. Those documents were unreachable by
    // construction: every read path goes through findAllByEventTypeIn(<the five known names>),
    // so no chart, grid, PDF or delete could ever see them again. They were pure growth in the
    // collection and its indexes, and their arrival was the only thing about them that could
    // have been useful - so that is what is kept, as one WARNING naming the offending type.
    if (!KNOWN_EVENT_TYPES.contains(data.getEventType())) {
      logger.warn("Dropping raw event with unrecognised eventType '{}' (known types are {}): {}",
          data.getEventType(), KNOWN_EVENT_TYPES, data);
      return;
    }

    if (data.getEventType().equals(EventNameEnum.FALL.name())) {
      List<User> users = userResponseDto2UserConverter.convert(userService.getAllUsers());
      for (User user : users) {
        logger.info("Sending fall notification to: {}", user.getEmail());
        try {
          mailService.sendUrgentEventMail(user, LocalDateTime.now(), data.getCameraName());
        } catch (Exception e) {
          // Isolated per recipient. Previously there was no try/catch at all, so the FIRST
          // unreachable mailbox ended the loop and every later user silently got nothing - and
          // because the save below sits after this block, the exception also escaped the listener
          // and the FALL was never written to MongoDB. A transient SMTP outage therefore deleted
          // the record of a person falling over, which is the one event in the system that must
          // survive everything else.
          //
          // Exception, not MessagingException: sendUrgentEventMail only DECLARES the checked
          // MessagingException, while the call that actually touches the network -
          // JavaMailSender.send - throws the unchecked org.springframework.mail.MailException.
          // Catching the declared type alone would leave the real-world failure (refused
          // connection, auth rejected, timeout) still aborting the loop.
          logger.error("Could not send fall notification to {}: {}", user.getEmail(), e.toString());
        }
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
      // Reached by exactly FALL, ARMS_UP and FRONT_BEND now - the countable family - because
      // anything not in KNOWN_EVENT_TYPES returned above. Before that guard existed this was also
      // the landing place for every unrecognised string on the topic.
      //
      // timePeriod is forced to null rather than passed through. This was the last document shape
      // in which "every stored duration is in milliseconds" was not true by construction: the
      // value was written verbatim, in whatever unit the producer happened to use and without a
      // schemaVersion to say which, while EventService divides every stored duration by 1000 on
      // the way out. A countable event that arrived carrying a raw `5` would have rendered as 0 s
      // in the events grid - where the design requires "-", because
      // toWholeSecondsOrNull(null) is what makes the cell empty - and the PDF would have printed
      // "Time Period: 0 s" for a fall.
      //
      // Null rather than normalise: a countable event has no duration to normalise. FALL, ARMS_UP
      // and FRONT_BEND are counted, never summed, so any number here is a measurement nobody took,
      // and stamping it with a unit would dignify it.
      //
      // Null rather than reject: dropping a FALL because a field was populated that should not
      // have been would recreate the data loss the mail isolation above exists to prevent. The
      // detector cannot produce this today (DetectionEvent.__post_init__ rejects a countable
      // event carrying a duration), but the topic is unauthenticated, so it is logged - the
      // arrival of one means some producer is not honouring the contract.
      if (data.getTimePeriod() != null) {
        logger.warn("Countable event {} from camera {} carried timePeriod={}; discarding the "
                + "duration - countable events have none. The event itself is still stored.",
            data.getEventType(), data.getCameraName(), data.getTimePeriod());
      }

      eventRepository.save(Event.builder()
          .eventType(data.getEventType())
          .startTime(data.getStartTime())
          .confidencePercentage(data.getConfidencePercentage())
          .cameraName(data.getCameraName())
          .timePeriod(null)
          .isProcessed(data.getIsProcessed())
          .build());
    }
  }
}
