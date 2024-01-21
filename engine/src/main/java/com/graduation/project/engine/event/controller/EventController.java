package com.graduation.project.engine.event.controller;

import com.graduation.project.engine.email.service.MailService;
import com.graduation.project.engine.event.model.Event;
import com.graduation.project.engine.event.model.response.CountableEvents;
import com.graduation.project.engine.event.model.response.PeriodicEvents;
import com.graduation.project.engine.event.model.response.PieChartResponseDto;
import com.graduation.project.engine.event.service.EventService;
import io.swagger.v3.oas.annotations.Operation;
import io.swagger.v3.oas.annotations.security.SecurityRequirement;
import java.io.ByteArrayOutputStream;
import java.io.File;
import java.util.List;
import lombok.RequiredArgsConstructor;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.core.io.FileSystemResource;
import org.springframework.http.MediaType;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.CrossOrigin;
import org.springframework.web.bind.annotation.DeleteMapping;
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
  @Value("${event.image.path}")
  private String imageFolderPath;


  @GetMapping("/countable-events/{startDate}/{endDate}")
  @Operation(
      description = "Get all countable events within a date range",
      summary = "Get Countable Events",
      security = @SecurityRequirement(name = "bearerAuth")
  )
  public List<CountableEvents> getAllCountableEvents(@PathVariable("startDate") Long startDate,
      @PathVariable("endDate") Long endDate) {

    return eventService.getAllCountableEventsByDateIntervals(startDate, endDate);
  }

  @GetMapping("/periodic-events/{startDate}/{endDate}")
  @Operation(
      description = "Get all periodic events within a date range",
      summary = "Get Periodic Events",
      security = @SecurityRequirement(name = "bearerAuth")
  )
  public List<PeriodicEvents> getAllPeriodicEvents(@PathVariable("startDate") Long startDate,
      @PathVariable("endDate") Long endDate) {

    return eventService.getAllPeriodicEventsByDateIntervals(startDate, endDate);
  }

  @DeleteMapping("/delete-events/{eventId}")
  @Operation(
      description = "Delete a specific event by ID",
      summary = "Delete Event",
      security = @SecurityRequirement(name = "bearerAuth")
  )
  public void getAllEvents(@PathVariable("eventId") String eventId) {
    eventService.deletePeriodicEventById(eventId);
  }

  @GetMapping("/all-events")
  @Operation(
      description = "Get all events",
      summary = "Get All Events",
      security = @SecurityRequirement(name = "bearerAuth")
  )
  public List<Event> getAllEvents() {
    return eventService.getAllEvents();
  }

  @PostMapping("/sendPdfEmail/{startDate}/{endDate}/{emailReceiver}")
  @Operation(
      description = "Send a PDF email containing events within a date range",
      summary = "Send PDF Email",
      security = @SecurityRequirement(name = "bearerAuth")
  )
  public ResponseEntity<String> sendPdfEmail(
      @PathVariable Long startDate, @PathVariable Long endDate,
      @PathVariable String emailReceiver) {
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

  @GetMapping("/pie-chart-events/{startDate}/{endDate}")
  @Operation(
      description = "Get pie chart data for events within a date range",
      summary = "Get Pie Chart Events",
      security = @SecurityRequirement(name = "bearerAuth")
  )
  public List<PieChartResponseDto> getPieChartEvents(@PathVariable("startDate") Long startDate,
      @PathVariable("endDate") Long endDate) {

    return eventService.getAllPieChartEventsByDateIntervals(startDate, endDate);
  }

  @GetMapping("/get_image/{timestamp}")
  public ResponseEntity<FileSystemResource> getImage(@PathVariable(name = "timestamp") long timestamp) {
    String imageName = "output_image.jpg";
    File imageFile = new File(imageFolderPath + imageName);

    if (imageFile.exists()) {
      return ResponseEntity.ok()
          .contentType(MediaType.IMAGE_JPEG)
          .body(new FileSystemResource(imageFile));
    } else {
      return ResponseEntity.notFound().build();
    }
  }
}
