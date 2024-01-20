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

  @KafkaListener(topics = "rawEvents", groupId = "groupId1")
  @SneakyThrows
  void listener(RawEvent data) {
    logger.info("Listener received: {} !", data);

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
