package com.graduation.project.engine.event.service;

import com.graduation.project.engine.core.exception.EntityNotFoundException;
import com.graduation.project.engine.event.model.EventNameEnum;
import com.graduation.project.engine.event.model.response.CountableEvents;
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
import lombok.RequiredArgsConstructor;
import org.springframework.stereotype.Service;

import java.util.List;

import static com.graduation.project.engine.core.exception.constant.ErrorConstant.USER_NOT_FOUND_MESSAGE;
import static com.graduation.project.engine.core.exception.constant.ErrorConstant.errorMessageParser;

@Service
@RequiredArgsConstructor
public class EventService {

  /**
   * The divisor for the storage-unit (milliseconds) to API-unit (seconds) conversion applied in
   * {@code calculatePeriodicEvents}. See {@code toWholeSeconds}.
   */
  private static final BigDecimal MILLIS_PER_SECOND = BigDecimal.valueOf(1000);

  private final EventRepository eventRepository;

  public List<Event> getAllEvents() {
    return eventRepository.findAll();
  }
  public void deletePeriodicEventById(String eventId) {
    eventRepository.findById(eventId).orElseThrow(
        () -> new EntityNotFoundException(errorMessageParser(USER_NOT_FOUND_MESSAGE, eventId)));
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
                ZoneId.systemDefault()).toLocalDate(),
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
          table.addCell("Time Period: " + event.getTimePeriod());
        }

        table.completeRow();
      }

      document.add(table);

      document.close();

      return byteArrayOutputStream;
    } catch (Exception e) {
      e.printStackTrace();
    }

    return byteArrayOutputStream;
  }


  private String getFormattedDateTime(Long timestamp) {
    return LocalDateTime.ofInstant(Instant.ofEpochMilli(timestamp), ZoneId.systemDefault())
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
      LocalDate eventDate = LocalDate.ofEpochDay(event.getStartTime() / (24 * 60 * 60 * 1000));
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

  private PeriodicEvents findPeriodicEventsByDate(List<PeriodicEvents> periodicEventsList,
      String date) {
    return periodicEventsList.stream()
        .filter(entry -> entry.getDate().equals(date))
        .findFirst()
        .orElse(null);
  }
}
