package com.graduation.project.engine.rawEvent.service;

import com.graduation.project.engine.event.model.Event;
import com.graduation.project.engine.event.repository.EventRepository;
import com.graduation.project.engine.rawEvent.model.RawEvent;
import lombok.RequiredArgsConstructor;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.kafka.annotation.KafkaListener;
import org.springframework.stereotype.Service;

@Service
@RequiredArgsConstructor
public class RawEventService {

  private final EventRepository eventRepository;

  Logger logger = LoggerFactory.getLogger(RawEventService.class);

  @KafkaListener(topics = "rawEvents", groupId = "groupId1")
  void listener(RawEvent data) {
    logger.info("Listener received: {} !", data);

    if (data.getEventType().equals("fall")) {
      //todo send email
    }
    if (data.getEventType().equals("armsUp")) {
      //countableEventsRepository.save(CountableEvents.builder().armsUp());
    }

    eventRepository.save(Event.builder()
        .eventType(data.getEventType())
        .startTime(data.getStartTime())
        .endTime(data.getEndTime())
        .cameraName(data.getCameraName())
        .timePeriod(data.getTimePeriod())
        .isProcessed(data.getIsProcessed())
        .build());
  }
}
