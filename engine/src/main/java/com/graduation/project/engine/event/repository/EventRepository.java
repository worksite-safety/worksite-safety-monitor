package com.graduation.project.engine.event.repository;

import com.graduation.project.engine.event.model.Event;
import java.math.BigDecimal;
import org.springframework.data.mongodb.repository.MongoRepository;

import java.util.List;
import org.springframework.data.mongodb.repository.Query;

public interface EventRepository extends MongoRepository<Event, String> {

    List<Event> findAllByEventTypeInAndStartTimeBetweenOrderByStartTimeAsc(List<String> eventType, Long startTime, Long endTime);

    int countEventsByEventType(String eventType);

}
