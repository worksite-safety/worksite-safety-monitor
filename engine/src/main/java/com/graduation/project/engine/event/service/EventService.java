package com.graduation.project.engine.event.service;

import com.graduation.project.engine.event.model.EventNameEnum;
import com.graduation.project.engine.event.model.response.CountableEvents;
import com.graduation.project.engine.event.model.Event;
import com.graduation.project.engine.event.model.response.PeriodicEvents;
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

@Service
@RequiredArgsConstructor
public class EventService {

  private final EventRepository eventRepository;

  public List<Event> getAllEvents() {
    return eventRepository.findAll();
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


  public List<PeriodicEvents> getAllPeriodicEventsByDateIntervals(Long startDate, Long endDate) {
    List<Event> eventList = getAllEventsByEventTypes(
        Arrays.asList(EventNameEnum.NO_HELMET.name(), EventNameEnum.NO_JACKET.name()),
        startDate, endDate);

    return calculatePeriodicEvents(eventList);
  }

  public List<Event> getAllEventsByDateIntervals(Long startDate, Long endDate) {
    return getAllEventsByEventTypes(
        Arrays.asList(EventNameEnum.FALL.name(), EventNameEnum.ARMS_UP.name(),
            EventNameEnum.FRONT_BEND.name(), EventNameEnum.NO_HELMET.name(), EventNameEnum.NO_JACKET.name()),
        startDate, endDate);
  }



  public ByteArrayOutputStream generateEventsPdf(List<Event> events, Long startDate, Long endDate) {
    ByteArrayOutputStream byteArrayOutputStream = new ByteArrayOutputStream();

    try {
      Document document = new Document();
      PdfWriter.getInstance(document, byteArrayOutputStream);
      document.open();
      document.addTitle("Requested Event Report");


      // Add Master Title
      Paragraph masterTitle = new Paragraph(
          "Event Report between " + getFormattedDateTime(startDate) +
              " and " + getFormattedDateTime(endDate),
          new Font(Font.FontFamily.HELVETICA, 18, Font.BOLD));
      masterTitle.setAlignment(Element.ALIGN_CENTER);
      document.add(masterTitle);

      document.add(new Paragraph("\n"));

      PdfPTable table = new PdfPTable(3);

      PdfPCell titleCellDate = new PdfPCell(new Phrase("Event Date"));
      PdfPCell titleCellType = new PdfPCell(new Phrase("Event Type"));
      PdfPCell titleCellDetails = new PdfPCell(new Phrase("Details"));

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
        .format(DateTimeFormatter.ofPattern("dd-MM-yyyy"));
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

      int noHelmetMinutes = 0;
      int noJacketMinutes = 0;

      if (EventNameEnum.NO_HELMET.name().equals(event.getEventType())) {
        noHelmetMinutes += event.getTimePeriod().intValue();
      } else if (EventNameEnum.NO_JACKET.name().equals(event.getEventType())) {
        noJacketMinutes += event.getTimePeriod().intValue();
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

  private PeriodicEvents findPeriodicEventsByDate(List<PeriodicEvents> periodicEventsList,
      String date) {
    return periodicEventsList.stream()
        .filter(entry -> entry.getDate().equals(date))
        .findFirst()
        .orElse(null);
  }
}
