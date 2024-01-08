package com.graduation.project.engine.event.service;

import com.graduation.project.engine.event.model.response.CountableEvents;
import com.graduation.project.engine.event.model.Event;
import com.graduation.project.engine.event.repository.EventRepository;
import java.time.Instant;
import java.time.LocalDate;
import java.time.LocalDateTime;
import java.time.ZoneId;
import java.time.format.DateTimeFormatter;
import java.util.ArrayList;
import java.util.Arrays;
import java.util.Collections;
import java.util.Comparator;
import java.util.Map;
import java.util.stream.Collectors;
import lombok.RequiredArgsConstructor;
import org.springframework.stereotype.Service;

import java.util.List;

@Service
@RequiredArgsConstructor
public class EventService {

  private final EventRepository eventRepository;

  public List<Event> getAllEvents() {
    return eventRepository.findAll();
  }

  public List<Event> getAllByEventTypes(List<String> eventTypes, Long startDate, Long endDate) {

    return eventRepository.findAllByEventTypeInAndStartTimeBetweenOrderByStartTimeAsc(eventTypes,
        startDate, endDate);
  }

  public List<CountableEvents> getAllCountableEventsByDateIntervals(Long startDate, Long endDate) {
    List<Event> eventList = getAllByEventTypes(Arrays.asList("fall", "arms-up", "front-bend"),
        startDate, endDate);

    Map<LocalDate, Map<String, Long>> groupedEvents = eventList.stream()
        .collect(Collectors.groupingBy(
            event -> LocalDateTime.ofInstant(Instant.ofEpochMilli(event.getStartTime()), ZoneId.systemDefault()).toLocalDate(),
            Collectors.groupingBy(Event::getEventType, Collectors.counting())
        ));


    List<CountableEvents> countableEventsList = new ArrayList<>();
    groupedEvents.forEach((date, eventCounts) -> {
      countableEventsList.add(CountableEvents.builder()
          .date(date.format(DateTimeFormatter.ofPattern("dd.MM.yyyy")))
          .fall(eventCounts.getOrDefault("fall", 0L).intValue())
          .armsUp(eventCounts.getOrDefault("arms-up", 0L).intValue())
          .frontBending(eventCounts.getOrDefault("front-bend", 0L).intValue())
          .build());
    });
    countableEventsList.sort(Comparator.comparing(
        event -> LocalDate.parse(event.getDate(), DateTimeFormatter.ofPattern("dd.MM.yyyy"))));

    return countableEventsList;
  }

}
