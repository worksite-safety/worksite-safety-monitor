package com.graduation.project.engine.event.controller;

import com.graduation.project.engine.email.service.MailService;
import com.graduation.project.engine.event.model.Event;
import com.graduation.project.engine.event.model.response.CountableEvents;
import com.graduation.project.engine.event.model.response.PeriodicEvents;
import com.graduation.project.engine.event.service.EventService;
import java.io.ByteArrayOutputStream;
import java.util.List;
import lombok.RequiredArgsConstructor;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.CrossOrigin;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/event")
@RequiredArgsConstructor
@CrossOrigin
public class EventController {

  private final EventService eventService;
  private final MailService mailService;


  @GetMapping("/countable-events/{startDate}/{endDate}")
  public List<CountableEvents> getAllCountableEvents(@PathVariable("startDate") Long startDate,
      @PathVariable("endDate") Long endDate) {

    return eventService.getAllCountableEventsByDateIntervals(startDate, endDate);
  }
  @GetMapping("/periodic-events/{startDate}/{endDate}")
  public List<PeriodicEvents> getAllPeriodicEvents(@PathVariable("startDate") Long startDate,
      @PathVariable("endDate") Long endDate) {

    return eventService.getAllPeriodicEventsByDateIntervals(startDate, endDate);
  }

  @GetMapping("/all-events")
  public List<Event> getAllEvents() {
    return eventService.getAllEvents();
  }

  @PostMapping("/sendPdfEmail/{startDate}/{endDate}/{emailReceiver}")
  public ResponseEntity<String> sendPdfEmail(
      @PathVariable Long startDate, @PathVariable Long endDate, @PathVariable String emailReceiver) {
    List<Event> events = eventService.getAllEventsByDateIntervals(startDate, endDate);
    ByteArrayOutputStream pdfStream = eventService.generateEventsPdf(events, startDate, endDate);

    try {
      mailService.sendEventsPdfEmail(emailReceiver, pdfStream.toByteArray());
      return ResponseEntity.ok("Email sent successfully!");
    } catch (Exception e) {
      e.printStackTrace();
      return ResponseEntity.status(500).body("Error sending email");
    }
  }
}
