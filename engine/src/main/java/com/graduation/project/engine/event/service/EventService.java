package com.graduation.project.engine.event.service;

import com.graduation.project.engine.core.exception.EntityNotFoundException;
import com.graduation.project.engine.event.model.EventNameEnum;
import com.graduation.project.engine.event.model.response.CountableEvents;
import com.graduation.project.engine.event.model.response.EventResponseDto;
import com.graduation.project.engine.event.model.Event;
import com.graduation.project.engine.event.model.response.PeriodicEvents;
import com.graduation.project.engine.event.model.response.PieChartResponseDto;
import com.graduation.project.engine.event.repository.EventRepository;
import com.itextpdf.text.Document;
import com.itextpdf.text.Element;
import com.itextpdf.text.Font;
import com.itextpdf.text.Paragraph;
import com.itextpdf.text.Phrase;
import com.itextpdf.text.pdf.PdfPCell;
import com.itextpdf.text.pdf.PdfPTable;
import com.itextpdf.text.pdf.PdfWriter;
import java.io.ByteArrayOutputStream;
import java.math.BigDecimal;
import java.math.RoundingMode;
import java.time.DateTimeException;
import java.time.Instant;
import java.time.LocalDate;
import java.time.LocalDateTime;
import java.time.ZoneId;
import java.time.format.DateTimeFormatter;
import java.util.ArrayList;
import java.util.Arrays;
import java.util.Comparator;
import java.util.Map;
import java.util.stream.Collectors;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.stereotype.Service;

import java.util.List;

import static com.graduation.project.engine.core.exception.constant.ErrorConstant.EVENT_NOT_FOUND_MESSAGE;
import static com.graduation.project.engine.core.exception.constant.ErrorConstant.errorMessageParser;

@Service
public class EventService {

  /**
   * The divisor for the storage-unit (milliseconds) to API-unit (seconds) conversion applied in
   * {@code calculatePeriodicEvents}. See {@code toWholeSeconds}.
   */
  private static final BigDecimal MILLIS_PER_SECOND = BigDecimal.valueOf(1000);

  private final EventRepository eventRepository;

  /**
   * The one zone in which this service decides what "day" an instant belongs to.
   *
   * <h2>What this replaced</h2>
   *
   * <p>Three sites, two different answers:
   *
   * <ul>
   *   <li>{@code getAllCountableEventsByDateIntervals} bucketed with {@code ZoneId.systemDefault()}
   *       - the JVM's zone, i.e. whatever the deployment host happens to be set to;</li>
   *   <li>{@code calculatePeriodicEvents} bucketed with
   *       {@code LocalDate.ofEpochDay(startTime / 86_400_000)} - integer division, i.e. hard-wired
   *       UTC, with no way to configure it;</li>
   *   <li>{@code getFormattedDateTime}, which stamps the emailed PDF report, used
   *       {@code systemDefault()} again.</li>
   * </ul>
   *
   * <p>So on any host not set to UTC, ONE event near midnight was counted on one day by the
   * countable chart and on the day before or after by the periodic chart - the two charts sit side
   * by side on the same dashboard, over the same range - while the PDF report emailed alongside
   * them agreed with neither reliably. Nothing failed; the numbers were simply attributed to
   * different days.
   *
   * <p>This survived because it is invisible in exactly the place it is usually looked for: on a
   * UTC CI runner all three agree and every assertion passes. It reproduces on the developers'
   * UTC+3 machines. {@code EventServiceTest.UnderAnExtremeJvmDefaultZone} is what closes that gap -
   * it forces the JVM default to UTC+14 and requires the answers to be unchanged.
   *
   * <h2>Why configurable, and why UTC by default</h2>
   *
   * <p>"Which day did this happen on" is a question about the worksite, not about the server, so
   * the answer has to be stated rather than inherited from whatever host the process lands on -
   * {@code systemDefault()} makes the same data produce different charts after a migration to a
   * differently-configured machine, with nothing in the output to say so. UTC is the default
   * because it is the one choice that is the same everywhere and matches what the periodic chart
   * already did, so an existing deployment's stored data keeps bucketing exactly as it did.
   * A site that wants local days sets {@code app.timezone} to its own zone and gets all three
   * surfaces moved together.
   */
  private final ZoneId reportingZone;

  public EventService(EventRepository eventRepository,
      @Value("${app.timezone:UTC}") String reportingZoneId) {
    this.eventRepository = eventRepository;

    if (reportingZoneId == null || reportingZoneId.isBlank()) {
      throw new IllegalStateException(
          "app.timezone is empty. Set it to an IANA zone id such as UTC or Europe/Istanbul.");
    }
    try {
      // Resolved once, at construction, so a typo ("Europe/Istanbol") stops the context from
      // starting instead of throwing on the first chart request. ZoneId.of also REJECTS the
      // three-letter abbreviations TimeZone.getTimeZone silently maps to GMT, so a misconfigured
      // zone cannot quietly degrade to UTC and look like it worked.
      this.reportingZone = ZoneId.of(reportingZoneId.trim());
    } catch (DateTimeException e) {
      throw new IllegalStateException(
          "app.timezone is not a valid IANA zone id: '" + reportingZoneId + "'", e);
    }
  }

  /**
   * Every stored event, as {@link EventResponseDto} - durations in SECONDS.
   *
   * <p>This used to be {@code return eventRepository.findAll()}: the MongoDB documents themselves,
   * serialised straight onto the wire. {@code Event.timePeriod} is milliseconds, so
   * {@code web/src/pages/Reporting.js} rendered every duration a thousand times too large in a
   * column headed "Time Period" while the periodic chart beside it, which converts, showed the
   * same events in seconds. The API contradicted itself.
   *
   * <p>The conversion is held here, at the same boundary as {@code calculatePeriodicEvents} and
   * with the same rounding rule ({@link #toWholeSeconds}: truncation, per event), so the grid and
   * the chart cannot disagree about the same event. See {@link EventResponseDto} for why the
   * conversion belongs in a DTO rather than in the entity or the frontend.
   *
   * <p>ASSUMPTION, shared with {@code calculatePeriodicEvents}: every stored duration is already
   * milliseconds. Documents predating {@code PeriodicTimePeriodMigration} hold seconds and would
   * be divided a second time. Deliberately NOT branched on {@code schemaVersion} here - the
   * periodic chart does not branch either, and a read path that disagreed with it would reinstate
   * the very inconsistency this change removes. Running the migration is the precondition for
   * both.
   */
  public List<EventResponseDto> getAllEvents() {
    return eventRepository.findAll().stream()
        .map(EventService::toResponseDto)
        .collect(Collectors.toList());
  }

  private static EventResponseDto toResponseDto(Event event) {
    return EventResponseDto.builder()
        .id(event.getId())
        .cameraName(event.getCameraName())
        .confidencePercentage(event.getConfidencePercentage())
        .eventType(event.getEventType())
        .startTime(event.getStartTime())
        .endTime(event.getEndTime())
        .timePeriod(toWholeSecondsOrNull(event.getTimePeriod()))
        .build();
  }
  public void deletePeriodicEventById(String eventId) {
    eventRepository.findById(eventId).orElseThrow(
        () -> new EntityNotFoundException(errorMessageParser(EVENT_NOT_FOUND_MESSAGE, eventId)));
    eventRepository.deleteById(eventId);

  }
  public List<CountableEvents> getAllCountableEventsByDateIntervals(Long startDate, Long endDate) {
    List<Event> eventList = getAllEventsByEventTypes(
        Arrays.asList(EventNameEnum.FALL.name(), EventNameEnum.ARMS_UP.name(),
            EventNameEnum.FRONT_BEND.name()),
        startDate, endDate);

    Map<LocalDate, Map<String, Long>> groupedEvents = eventList.stream()
        .collect(Collectors.groupingBy(
            event -> LocalDateTime.ofInstant(Instant.ofEpochMilli(event.getStartTime()),
                reportingZone).toLocalDate(),
            Collectors.groupingBy(Event::getEventType, Collectors.counting())
        ));

    List<CountableEvents> countableEventsList = new ArrayList<>();
    groupedEvents.forEach((date, eventCounts) -> {
      countableEventsList.add(CountableEvents.builder()
          .date(date.format(DateTimeFormatter.ofPattern("dd.MM.yyyy")))
          .fall(eventCounts.getOrDefault(EventNameEnum.FALL.name(), 0L).intValue())
          .armsUp(eventCounts.getOrDefault(EventNameEnum.ARMS_UP.name(), 0L).intValue())
          .frontBending(eventCounts.getOrDefault(EventNameEnum.FRONT_BEND.name(), 0L).intValue())
          .build());
    });
    countableEventsList.sort(Comparator.comparing(
        event -> LocalDate.parse(event.getDate(), DateTimeFormatter.ofPattern("dd.MM.yyyy"))));

    return countableEventsList;
  }

  public List<PieChartResponseDto> getAllPieChartEventsByDateIntervals(Long startDate,
      Long endDate) {
    List<EventNameEnum> requiredEventTypes = Arrays.asList(
        EventNameEnum.FALL,
        EventNameEnum.ARMS_UP,
        EventNameEnum.FRONT_BEND
    );

    List<Event> eventList = getAllEventsByEventTypes(requiredEventTypes.stream()
        .map(Enum::name)
        .collect(Collectors.toList()), startDate, endDate);

    Map<EventNameEnum, Long> eventTypeCountMap = eventList.stream()
        .collect(Collectors.groupingBy(
            event -> EventNameEnum.valueOf(event.getEventType()),
            Collectors.counting()
        ));

    List<PieChartResponseDto> result = requiredEventTypes.stream()
        .map(eventType -> PieChartResponseDto.builder()
            .name(eventType.name())
            .value(eventTypeCountMap.getOrDefault(eventType, 0L).intValue())
            .build())
        .collect(Collectors.toList());

    return result;
  }


  public List<PeriodicEvents> getAllPeriodicEventsByDateIntervals(Long startDate, Long endDate) {
    List<Event> eventList = getAllEventsByEventTypes(
        Arrays.asList(EventNameEnum.NO_HELMET.name(), EventNameEnum.NO_JACKET.name()),
        startDate, endDate);

    return calculatePeriodicEvents(eventList);
  }



  public List<Event> getAllEventsByDateIntervals(Long startDate, Long endDate) {
    return getAllEventsByEventTypes(
        Arrays.asList(EventNameEnum.FALL.name(), EventNameEnum.ARMS_UP.name(),
            EventNameEnum.FRONT_BEND.name(), EventNameEnum.NO_HELMET.name(),
            EventNameEnum.NO_JACKET.name()),
        startDate, endDate);
  }


  /**
   * Renders {@code events} into a PDF held entirely in memory.
   *
   * <h2>This method either returns a PDF or throws</h2>
   *
   * <p>It used to have a third outcome, and that was the defect. The {@code catch} called
   * {@code printStackTrace()} and returned the {@link ByteArrayOutputStream} it had been writing
   * into. Because iText buffers the document until {@link Document#close()} - which the error path
   * never reaches - the stream came back with ZERO bytes rather than a partial document.
   * {@code EventController.sendPdfEmail} could not tell the difference, so it attached the empty
   * byte array, sent it, and answered {@code 200 "Email sent successfully!"}. The operator got a
   * success toast and an unopenable 0-byte attachment.
   *
   * <p>The catch now wraps and rethrows as {@link ReportGenerationException}, so "no report" is a
   * signal the caller must handle rather than a value it cannot distinguish from success. The
   * cause is attached, so the diagnosis that used to land on stdout travels with the failure.
   *
   * @throws ReportGenerationException if the document cannot be produced, for any reason
   */
  public ByteArrayOutputStream generateEventsPdf(List<Event> events, Long startDate, Long endDate) {
    ByteArrayOutputStream byteArrayOutputStream = new ByteArrayOutputStream();

    try {
      Document document = new Document();
      PdfWriter.getInstance(document, byteArrayOutputStream);
      document.open();
      document.addTitle("Requested Event Report");

      Paragraph masterTitle = new Paragraph(
          "Event Report between " + getFormattedDateTime(startDate) +
              " and " + getFormattedDateTime(endDate),
          new Font(Font.FontFamily.HELVETICA, 18, Font.BOLD));
      masterTitle.setAlignment(Element.ALIGN_CENTER);
      document.add(masterTitle);

      document.add(new Paragraph("\n"));

      PdfPTable table = new PdfPTable(3);

      Font boldFont = new Font(Font.FontFamily.HELVETICA, 12, Font.BOLD);

      PdfPCell titleCellDate = new PdfPCell(new Phrase("Event Date", boldFont));
      PdfPCell titleCellType = new PdfPCell(new Phrase("Event Type", boldFont));
      PdfPCell titleCellDetails = new PdfPCell(new Phrase("Details", boldFont));

      table.addCell(titleCellDate);
      table.addCell(titleCellType);
      table.addCell(titleCellDetails);

      table.completeRow();

      for (Event event : events) {
        table.addCell(getFormattedDateTime(event.getStartTime()));
        table.addCell(event.getEventType());

        if (EventNameEnum.NO_HELMET.name().equals(event.getEventType()) ||
            EventNameEnum.NO_JACKET.name().equals(event.getEventType())) {
          // SECONDS, via the same truncation the periodic chart and the events grid use. This
          // printed event.getTimePeriod() verbatim, i.e. the stored MILLISECONDS, so a 5-second
          // violation reached the operator's inbox as "Time Period: 5000" while the dashboard
          // they had just been looking at said 5. The unit is spelled out in the cell because
          // this document is read away from the application, with nothing beside it to compare
          // against - an unlabelled number here is exactly how the mismatch went unnoticed.
          table.addCell("Time Period: " + toWholeSeconds(event.getTimePeriod()) + " s");
        }

        table.completeRow();
      }

      document.add(table);

      document.close();

      return byteArrayOutputStream;
    } catch (Exception e) {
      throw new ReportGenerationException(
          "Failed to generate the events PDF for " + events.size() + " event(s) between "
              + startDate + " and " + endDate, e);
    }
  }


  private String getFormattedDateTime(Long timestamp) {
    return LocalDateTime.ofInstant(Instant.ofEpochMilli(timestamp), reportingZone)
        .format(DateTimeFormatter.ofPattern("dd-MM-yyyy HH:mm:ss"));
  }


  private List<Event> getAllEventsByEventTypes(List<String> eventTypes, Long startDate,
      Long endDate) {

    return eventRepository.findAllByEventTypeInAndStartTimeBetweenOrderByStartTimeAsc(eventTypes,
        startDate, endDate);
  }

  private List<PeriodicEvents> calculatePeriodicEvents(List<Event> eventList) {
    List<PeriodicEvents> periodicEventsList = new ArrayList<>();

    for (Event event : eventList) {
      // Was LocalDate.ofEpochDay(startTime / (24 * 60 * 60 * 1000)) - hard-wired UTC, and not
      // merely because of the constant: integer division truncates TOWARDS ZERO, so any timestamp
      // before 1970 also landed a day late. Going through Instant/ZoneId fixes both and is the
      // same expression the countable endpoint uses, which is the point - one zone, one answer.
      LocalDate eventDate = Instant.ofEpochMilli(event.getStartTime())
          .atZone(reportingZone).toLocalDate();
      String formattedDate = eventDate.format(DateTimeFormatter.ofPattern("dd.MM.yyyy"));

      // The local names say "Minutes" and the values are seconds. Left alone deliberately: this
      // slice changes the storage unit, and renaming locals in the same commit would hide that
      // diff. The numbers are pinned by EventServiceTest.
      int noHelmetMinutes = 0;
      int noJacketMinutes = 0;

      if (EventNameEnum.NO_HELMET.name().equals(event.getEventType())) {
        noHelmetMinutes += toWholeSeconds(event.getTimePeriod());
      } else if (EventNameEnum.NO_JACKET.name().equals(event.getEventType())) {
        noJacketMinutes += toWholeSeconds(event.getTimePeriod());
      }

      PeriodicEvents existingEntry = findPeriodicEventsByDate(periodicEventsList, formattedDate);

      if (existingEntry != null) {
        existingEntry.setNoHelmet(existingEntry.getNoHelmet() + noHelmetMinutes);
        existingEntry.setNoJacket(existingEntry.getNoJacket() + noJacketMinutes);
      } else {
        PeriodicEvents newEntry = PeriodicEvents.builder()
            .date(formattedDate)
            .noHelmet(noHelmetMinutes)
            .noJacket(noJacketMinutes)
            .build();
        periodicEventsList.add(newEntry);
      }
    }

    return periodicEventsList;
  }

  /**
   * Converts one stored duration from milliseconds to whole seconds.
   *
   * <h2>Why the conversion is here and not in the response DTO or the frontend</h2>
   *
   * <p>{@code Event.timePeriod} is milliseconds from this slice onwards. The dashboard plots
   * {@code noHelmet}/{@code noJacket} raw - there is no unit conversion anywhere in
   * {@code web/src/pages/ChartsContainer.js} - so returning the stored value would make every
   * periodic chart 1000x taller with no code change on the frontend, no error, and nothing in a
   * log to say why. The API contract stays in seconds and the field names are unchanged, so the
   * storage unit moved without the dashboard noticing.
   *
   * <h2>Rounding: TRUNCATION, per event</h2>
   *
   * <p>{@link RoundingMode#DOWN}, applied to each event before the day's total is accumulated.
   * A 2999 ms window is reported as 2 seconds, not 3.
   *
   * <p>Per event rather than per day-bucket because that is what this endpoint already did -
   * {@code intValue()} truncated every value before summing it, so "5.9 + 5.9 = 10" was already
   * the pinned behaviour. Keeping the same rounding point means this slice changes the unit and
   * only the unit. The cost is that the error compounds: N events lose up to N seconds in total,
   * where summing first and dividing once would lose under one second per day. That is a real
   * under-report and it is recorded in
   * {@code EventServiceTest#periodic_truncationErrorCompoundsPerEvent}.
   *
   * <p>The division happens on the {@link BigDecimal}, not after an {@code intValue()}.
   * {@code BigDecimal.intValue()} returns the low-order 32 bits when the value does not fit, so
   * converting first would report a 34.7 day violation as {@code -1294967296} seconds - a negative
   * bar on a safety chart.
   */
  private static int toWholeSeconds(BigDecimal timePeriodMillis) {
    if (timePeriodMillis == null) {
      return 0;
    }
    return timePeriodMillis.divide(MILLIS_PER_SECOND, 0, RoundingMode.DOWN).intValue();
  }

  /**
   * {@link #toWholeSeconds} for the paths that must PRESERVE the absence of a duration.
   *
   * <p>The chart sums durations, so "no duration" and "zero duration" are the same thing there and
   * {@code toWholeSeconds} collapses null to 0. A row in the events grid is not a sum: FALL,
   * ARMS_UP and FRONT_BEND have no duration at all, and reporting 0 for them would assert a
   * zero-second violation that was never measured. The grid renders
   * {@code row.timePeriod === null ? '-' : row.timePeriod}, so null is what makes the cell read
   * "-".
   */
  private static Integer toWholeSecondsOrNull(BigDecimal timePeriodMillis) {
    return timePeriodMillis == null ? null : toWholeSeconds(timePeriodMillis);
  }

  private PeriodicEvents findPeriodicEventsByDate(List<PeriodicEvents> periodicEventsList,
      String date) {
    return periodicEventsList.stream()
        .filter(entry -> entry.getDate().equals(date))
        .findFirst()
        .orElse(null);
  }
}
