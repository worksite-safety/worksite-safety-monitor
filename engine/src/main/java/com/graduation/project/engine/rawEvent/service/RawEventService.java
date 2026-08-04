package com.graduation.project.engine.rawEvent.service;

import com.graduation.project.engine.email.service.MailService;
import com.graduation.project.engine.event.model.Event;
import com.graduation.project.engine.event.model.EventNameEnum;
import com.graduation.project.engine.event.repository.EventRepository;
import com.graduation.project.engine.rawEvent.model.RawEvent;
import com.graduation.project.engine.user.model.User;
import com.graduation.project.engine.user.model.converter.UserResponseDto2UserConverter;
import com.graduation.project.engine.user.service.UserService;
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
  @Value("${event.fall.threshold.value}")
  private int fallEventThreshold;

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
      if (data.getTimePeriod().intValue() > fallEventThreshold) {
        eventRepository.save(Event.builder()
            .eventType(data.getEventType())
            .startTime(data.getStartTime())
            .confidencePercentage(data.getConfidencePercentage())
            .cameraName(data.getCameraName())
            .timePeriod(data.getTimePeriod())
            .isProcessed(data.getIsProcessed())
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
