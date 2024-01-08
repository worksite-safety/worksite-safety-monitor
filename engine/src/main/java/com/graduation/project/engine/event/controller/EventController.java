package com.graduation.project.engine.event.controller;

import com.graduation.project.engine.event.model.Event;
import com.graduation.project.engine.event.model.response.CountableEvents;
import com.graduation.project.engine.event.service.EventService;
import java.util.List;
import lombok.RequiredArgsConstructor;
import org.springframework.web.bind.annotation.CrossOrigin;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/event")
@RequiredArgsConstructor
@CrossOrigin
public class EventController {

  private final EventService eventService;


  @GetMapping("/countable-events/{startDate}/{endDate}")
  public List<CountableEvents> getAllCountableEvents(@PathVariable("startDate") Long startDate,
      @PathVariable("endDate") Long endDate) {

    return eventService.getAllCountableEventsByDateIntervals(startDate, endDate);
  }

  @GetMapping("/all-events")
  public List<Event> getAllEvents() {
    return eventService.getAllEvents();
  }
}
