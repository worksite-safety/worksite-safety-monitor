package com.graduation.project.engine.event.repository;

import com.graduation.project.engine.event.model.Event;
import org.springframework.data.mongodb.repository.MongoRepository;

import java.util.List;

public interface EventRepository extends MongoRepository<Event, String> {

  List<Event> findAllByEventTypeInAndStartTimeBetweenOrderByStartTimeAsc(List<String> eventType,
      Long startTime, Long endTime);
}
