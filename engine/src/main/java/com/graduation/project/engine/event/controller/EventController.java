package com.graduation.project.engine.event.controller;

import com.graduation.project.engine.email.service.MailService;
import com.graduation.project.engine.event.model.Event;
import com.graduation.project.engine.event.model.response.CountableEvents;
import com.graduation.project.engine.event.model.response.EventResponseDto;
import com.graduation.project.engine.event.model.response.PeriodicEvents;
import com.graduation.project.engine.event.model.response.PieChartResponseDto;
import com.graduation.project.engine.event.service.EventService;
import com.graduation.project.engine.event.service.ReportGenerationException;
import io.swagger.v3.oas.annotations.Operation;
import io.swagger.v3.oas.annotations.security.SecurityRequirement;
import java.io.File;
import java.util.List;
import lombok.RequiredArgsConstructor;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
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

  private static final Logger logger = LoggerFactory.getLogger(EventController.class);

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
  public List<EventResponseDto> getAllEvents() {
    return eventService.getAllEvents();
  }

  /**
   * Builds the events report for a date range and mails it.
   *
   * <h2>Three outcomes, three answers</h2>
   *
   * <p>There used to be one answer. The report was generated, the bytes were attached whatever
   * they were, and the response was {@code 200 "Email sent successfully!"}. Since
   * {@code EventService.generateEventsPdf} swallowed its own failures and returned a ZERO-BYTE
   * stream, the common failure mode was: operator clicks "Send Report", sees "Report sent
   * successfully!", and receives a mail with an unopenable 0-byte {@code events_data.pdf}. The
   * only record of what went wrong was a stack trace on stdout.
   *
   * <p>Now:
   * <ul>
   *   <li>report could not be built -> {@code 500}, and NO mail is composed at all;</li>
   *   <li>report built but the mail failed -> {@code 500}, with its own message, because
   *       "cannot render" and "cannot deliver" are different problems for whoever is on call;</li>
   *   <li>report built and sent -> {@code 200}, which now means it.</li>
   * </ul>
   *
   * <p>The empty-stream guard is kept even though {@code generateEventsPdf} now throws instead of
   * returning empty: it is the assertion that a success response implies an actual attachment, at
   * the one place that assertion protects a user-visible claim.
   *
   * <p>{@code web/src/pages/Reporting.js} shows its "Report sent successfully!" toast on any 2xx
   * and logs on anything else, so a 500 here is already enough to stop the false success message
   * without touching the frontend.
   */
  @PostMapping("/sendPdfEmail/{startDate}/{endDate}/{emailReceiver}")
  @Operation(
      description = "Send a PDF email containing events within a date range",
      summary = "Send PDF Email",
      security = @SecurityRequirement(name = "bearerAuth")
  )
  public ResponseEntity<String> sendPdfEmail(
      @PathVariable Long startDate, @PathVariable Long endDate,
      @PathVariable String emailReceiver) {

    byte[] pdf;
    try {
      List<Event> events = eventService.getAllEventsByDateIntervals(startDate, endDate);
      pdf = eventService.generateEventsPdf(events, startDate, endDate).toByteArray();
    } catch (ReportGenerationException e) {
      // Logged, not printStackTrace()d: a stack trace on stdout is exactly how this failure
      // stayed invisible for as long as it did.
      logger.error("Report generation failed for range {}..{}, requested by {}. No email sent.",
          startDate, endDate, emailReceiver, e);
      return ResponseEntity.status(500)
          .body("The report could not be generated, so no email was sent.");
    }

    if (pdf.length == 0) {
      logger.error("Refusing to email an empty report for range {}..{}, requested by {}.",
          startDate, endDate, emailReceiver);
      return ResponseEntity.status(500)
          .body("The report came back empty, so no email was sent.");
    }

    try {
      mailService.sendEventsPdfEmail(emailReceiver, pdf);
      return ResponseEntity.ok("Email sent successfully!");
    } catch (Exception e) {
      logger.error("Report generated but sending it to {} failed.", emailReceiver, e);
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
