package com.graduation.project.engine.event.service;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;
import static org.assertj.core.api.Assertions.tuple;
import static org.mockito.ArgumentMatchers.eq;
import static org.mockito.Mockito.never;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.when;

import com.fasterxml.jackson.databind.ObjectMapper;
import com.graduation.project.engine.core.exception.EntityNotFoundException;
import com.graduation.project.engine.event.model.Event;
import com.graduation.project.engine.event.model.EventNameEnum;
import com.graduation.project.engine.event.model.response.CountableEvents;
import com.graduation.project.engine.event.model.response.EventResponseDto;
import com.graduation.project.engine.event.model.response.PeriodicEvents;
import com.graduation.project.engine.event.model.response.PieChartResponseDto;
import com.graduation.project.engine.event.repository.EventRepository;
import com.itextpdf.text.pdf.PdfReader;
import com.itextpdf.text.pdf.parser.PdfTextExtractor;
import java.io.ByteArrayOutputStream;
import java.math.BigDecimal;
import java.nio.charset.StandardCharsets;
import java.time.LocalDateTime;
import java.time.ZoneOffset;
import java.util.Arrays;
import java.util.List;
import java.util.Optional;
import java.util.TimeZone;
import org.junit.jupiter.api.AfterEach;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.DisplayName;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.extension.ExtendWith;
import org.mockito.ArgumentCaptor;
import org.mockito.Captor;
import org.mockito.InjectMocks;
import org.mockito.Mock;
import org.mockito.junit.jupiter.MockitoExtension;

/**
 * Characterization tests for {@link EventService}.
 *
 * <p>These pin CURRENT behaviour ahead of a Spring Boot 3.0.4 -> 3.5.x upgrade. Several of the
 * behaviours pinned here are arguably wrong (see the {@code @DisplayName}s that say so); they are
 * recorded, not fixed.
 *
 * <p><b>Time zone discipline.</b> {@code getAllCountableEventsByDateIntervals} buckets days with
 * {@link java.time.ZoneId#systemDefault()} while {@code calculatePeriodicEvents} buckets with
 * integer division by 86_400_000 (i.e. hard-wired UTC). Every day-bucketing assertion below
 * therefore pins the JVM default zone explicitly in {@link #setUp()} and restores the real one in
 * {@link #tearDown()}, so nothing here silently depends on the machine's zone.
 */
@ExtendWith(MockitoExtension.class)
class EventServiceTest {

  private static final Long START = 1_600_000_000_000L;
  private static final Long END = 1_800_000_000_000L;

  private static final List<String> COUNTABLE_TYPES = Arrays.asList("FALL", "ARMS_UP",
      "FRONT_BEND");
  private static final List<String> PERIODIC_TYPES = Arrays.asList("NO_HELMET", "NO_JACKET");
  private static final List<String> ALL_TYPES = Arrays.asList("FALL", "ARMS_UP", "FRONT_BEND",
      "NO_HELMET", "NO_JACKET");

  @Mock
  private EventRepository eventRepository;

  @InjectMocks
  private EventService eventService;

  @Captor
  private ArgumentCaptor<List<String>> eventTypesCaptor;

  private TimeZone originalTimeZone;

  @BeforeEach
  void setUp() {
    originalTimeZone = TimeZone.getDefault();
    // Default for most tests: UTC, so the system-default-zone path and the hard-wired-UTC path
    // agree and each test measures only what it means to measure. The two tests that exist to
    // pin the disagreement override this locally.
    TimeZone.setDefault(TimeZone.getTimeZone("UTC"));
  }

  @AfterEach
  void tearDown() {
    TimeZone.setDefault(originalTimeZone);
  }

  // ---------------------------------------------------------------------------------------------
  // getAllCountableEventsByDateIntervals
  // ---------------------------------------------------------------------------------------------

  @Test
  @DisplayName("countable: groups by day, counts per type, formats the date as dd.MM.yyyy")
  void countable_groupsByDayAndCountsPerType() {
    stubCountable(
        countable(EventNameEnum.FALL, utc(2023, 11, 14, 8, 0)),
        countable(EventNameEnum.FALL, utc(2023, 11, 14, 9, 30)),
        countable(EventNameEnum.ARMS_UP, utc(2023, 11, 14, 23, 59)),
        countable(EventNameEnum.FRONT_BEND, utc(2023, 11, 16, 0, 0)));

    List<CountableEvents> result = eventService.getAllCountableEventsByDateIntervals(START, END);

    assertThat(result).hasSize(2);
    assertThat(result.get(0).getDate()).isEqualTo("14.11.2023");
    assertThat(result.get(0).getFall()).isEqualTo(2);
    assertThat(result.get(0).getArmsUp()).isEqualTo(1);
    assertThat(result.get(0).getFrontBending()).isZero();
    assertThat(result.get(1).getDate()).isEqualTo("16.11.2023");
    assertThat(result.get(1).getFall()).isZero();
    assertThat(result.get(1).getArmsUp()).isZero();
    assertThat(result.get(1).getFrontBending()).isEqualTo(1);
  }

  @Test
  @DisplayName("countable: days with no events are ABSENT - there is no gap filling")
  void countable_daysWithoutEventsAreAbsent() {
    stubCountable(
        countable(EventNameEnum.FALL, utc(2023, 11, 14, 12, 0)),
        countable(EventNameEnum.FALL, utc(2023, 11, 20, 12, 0)));

    List<CountableEvents> result = eventService.getAllCountableEventsByDateIntervals(START, END);

    // 15.11 .. 19.11 are simply missing rather than present with zeros.
    assertThat(result).extracting(CountableEvents::getDate)
        .containsExactly("14.11.2023", "20.11.2023");
  }

  @Test
  @DisplayName("countable: sorts ascending by date regardless of the order the repository returns")
  void countable_sortsAscendingRegardlessOfRepositoryOrder() {
    stubCountable(
        countable(EventNameEnum.FALL, utc(2023, 12, 3, 10, 0)),
        countable(EventNameEnum.FALL, utc(2023, 11, 14, 10, 0)),
        countable(EventNameEnum.FALL, utc(2024, 1, 5, 10, 0)),
        countable(EventNameEnum.FALL, utc(2023, 11, 30, 10, 0)));

    List<CountableEvents> result = eventService.getAllCountableEventsByDateIntervals(START, END);

    assertThat(result).extracting(CountableEvents::getDate)
        .containsExactly("14.11.2023", "30.11.2023", "03.12.2023", "05.01.2024");
  }

  @Test
  @DisplayName("countable: dd.MM.yyyy is zero padded (05.01.2024, not 5.1.2024)")
  void countable_dateFormatIsZeroPadded() {
    stubCountable(countable(EventNameEnum.ARMS_UP, utc(2024, 1, 5, 6, 7)));

    List<CountableEvents> result = eventService.getAllCountableEventsByDateIntervals(START, END);

    assertThat(result).singleElement()
        .extracting(CountableEvents::getDate)
        .isEqualTo("05.01.2024");
  }

  @Test
  @DisplayName("countable: no matching events -> EMPTY list (contrast with the pie chart endpoint)")
  void countable_noEventsReturnsEmptyList() {
    stubCountable();

    assertThat(eventService.getAllCountableEventsByDateIntervals(START, END)).isEmpty();
  }

  @Test
  @DisplayName("countable: queries the repository with exactly [FALL, ARMS_UP, FRONT_BEND]")
  void countable_queriesOnlyCountableTypes() {
    stubCountable();

    eventService.getAllCountableEventsByDateIntervals(START, END);

    verify(eventRepository).findAllByEventTypeInAndStartTimeBetweenOrderByStartTimeAsc(
        eventTypesCaptor.capture(), eq(START), eq(END));
    assertThat(eventTypesCaptor.getValue()).containsExactly("FALL", "ARMS_UP", "FRONT_BEND");
  }

  @Test
  @DisplayName("countable: buckets the day in the JVM DEFAULT zone (not UTC)")
  void countable_bucketsDayInSystemDefaultZone() {
    // 2023-11-14T02:00Z is still 2023-11-13 21:00 in New York (EST, UTC-5).
    TimeZone.setDefault(TimeZone.getTimeZone("America/New_York"));
    stubCountable(countable(EventNameEnum.FALL, utc(2023, 11, 14, 2, 0)));

    List<CountableEvents> result = eventService.getAllCountableEventsByDateIntervals(START, END);

    assertThat(result).singleElement()
        .extracting(CountableEvents::getDate)
        .isEqualTo("13.11.2023");
  }

  // ---------------------------------------------------------------------------------------------
  // getAllPieChartEventsByDateIntervals
  // ---------------------------------------------------------------------------------------------

  @Test
  @DisplayName("pie chart: ALWAYS returns all three countable types, in declaration order, 0 for missing")
  void pieChart_alwaysReturnsAllThreeTypes() {
    stubCountable(
        countable(EventNameEnum.ARMS_UP, utc(2023, 11, 14, 8, 0)),
        countable(EventNameEnum.ARMS_UP, utc(2023, 11, 15, 8, 0)),
        countable(EventNameEnum.ARMS_UP, utc(2023, 11, 16, 8, 0)));

    List<PieChartResponseDto> result = eventService.getAllPieChartEventsByDateIntervals(START, END);

    assertThat(result).extracting(PieChartResponseDto::getName)
        .containsExactly("FALL", "ARMS_UP", "FRONT_BEND");
    assertThat(result).extracting(PieChartResponseDto::getValue)
        .containsExactly(0, 3, 0);
  }

  @Test
  @DisplayName("pie chart vs countable ASYMMETRY: same empty input -> 3 zero rows vs an empty list")
  void pieChart_emptyInputAsymmetryWithCountable() {
    stubCountable();

    List<PieChartResponseDto> pie = eventService.getAllPieChartEventsByDateIntervals(START, END);
    List<CountableEvents> countable = eventService.getAllCountableEventsByDateIntervals(START, END);

    // This is the asymmetry the frontend has to cope with: /pie-chart-events never returns an
    // empty array, /countable-events does.
    assertThat(pie).hasSize(3);
    assertThat(pie).extracting(PieChartResponseDto::getValue).containsExactly(0, 0, 0);
    assertThat(countable).isEmpty();
  }

  @Test
  @DisplayName("pie chart: aggregates over the WHOLE range - day boundaries are ignored")
  void pieChart_aggregatesAcrossTheWholeRange() {
    stubCountable(
        countable(EventNameEnum.FALL, utc(2023, 11, 14, 8, 0)),
        countable(EventNameEnum.FALL, utc(2023, 12, 25, 8, 0)),
        countable(EventNameEnum.FRONT_BEND, utc(2024, 1, 5, 8, 0)));

    List<PieChartResponseDto> result = eventService.getAllPieChartEventsByDateIntervals(START, END);

    assertThat(result).extracting(PieChartResponseDto::getName, PieChartResponseDto::getValue)
        .containsExactly(tuple("FALL", 2), tuple("ARMS_UP", 0), tuple("FRONT_BEND", 1));
  }

  @Test
  @DisplayName("pie chart: queries the repository with exactly [FALL, ARMS_UP, FRONT_BEND]")
  void pieChart_queriesOnlyCountableTypes() {
    stubCountable();

    eventService.getAllPieChartEventsByDateIntervals(START, END);

    verify(eventRepository).findAllByEventTypeInAndStartTimeBetweenOrderByStartTimeAsc(
        eventTypesCaptor.capture(), eq(START), eq(END));
    assertThat(eventTypesCaptor.getValue()).containsExactly("FALL", "ARMS_UP", "FRONT_BEND");
  }

  // ---------------------------------------------------------------------------------------------
  // getAllPeriodicEventsByDateIntervals
  // ---------------------------------------------------------------------------------------------

  /**
   * NOTE ON THIS TEST AND THE ONE BELOW.
   *
   * <p>The ASSERTED NUMBERS ARE UNCHANGED - still 12, 3, 11 here and still 10 below. What changed
   * is the FIXTURE: {@code timePeriod} is now stored in milliseconds, so the values that used to
   * read "5", "7", "3", "11" now read "5000", "7000", "3000", "11000". The response is still
   * seconds and still carries the field names {@code noHelmet}/{@code noJacket}, so nothing the
   * dashboard sees has moved.
   *
   * <p>That is the whole intent of holding the conversion at this boundary: the storage unit
   * changed underneath and the API did not.
   */
  @Test
  @DisplayName("periodic: sums timePeriod per day, per type - stored ms, reported SECONDS")
  void periodic_sumsTimePeriodPerDayPerType() {
    stubPeriodic(
        periodic(EventNameEnum.NO_HELMET, utc(2023, 11, 14, 8, 0), "5000"),
        periodic(EventNameEnum.NO_HELMET, utc(2023, 11, 14, 9, 0), "7000"),
        periodic(EventNameEnum.NO_JACKET, utc(2023, 11, 14, 10, 0), "3000"),
        periodic(EventNameEnum.NO_JACKET, utc(2023, 11, 15, 10, 0), "11000"));

    List<PeriodicEvents> result = eventService.getAllPeriodicEventsByDateIntervals(START, END);

    assertThat(result).hasSize(2);
    assertThat(result.get(0).getDate()).isEqualTo("14.11.2023");
    assertThat(result.get(0).getNoHelmet()).isEqualTo(12);
    assertThat(result.get(0).getNoJacket()).isEqualTo(3);
    assertThat(result.get(1).getDate()).isEqualTo("15.11.2023");
    assertThat(result.get(1).getNoHelmet()).isZero();
    assertThat(result.get(1).getNoJacket()).isEqualTo(11);
  }

  @Test
  @DisplayName("periodic: each event is TRUNCATED to whole seconds BEFORE being summed, not rounded")
  void periodic_truncatesFractionalTimePeriodPerEvent() {
    stubPeriodic(
        periodic(EventNameEnum.NO_HELMET, utc(2023, 11, 14, 8, 0), "5900"),
        periodic(EventNameEnum.NO_HELMET, utc(2023, 11, 14, 9, 0), "5900"));

    List<PeriodicEvents> result = eventService.getAllPeriodicEventsByDateIntervals(START, END);

    // 5900 ms + 5900 ms = 11.8 s, but each event is truncated to 5 s BEFORE being summed -> 10.
    // Identical to the pre-migration behaviour, where each "5.9" was truncated by intValue().
    assertThat(result).singleElement()
        .extracting(PeriodicEvents::getNoHelmet)
        .isEqualTo(10);
  }

  // ---------------------------------------------------------------------------------------------
  // The ms -> s boundary. These are new, and they exist because the conversion is a DECISION with
  // a visible cost, not a detail: truncation is applied PER EVENT, so the loss compounds with the
  // number of events rather than being bounded per day.
  // ---------------------------------------------------------------------------------------------

  @Test
  @DisplayName("periodic: rounding is TRUNCATION - a 2999 ms window reports as 2 seconds, not 3")
  void periodic_2999MillisecondsTruncatesToTwoSeconds() {
    stubPeriodic(periodic(EventNameEnum.NO_HELMET, utc(2023, 11, 14, 8, 0), "2999"));

    assertThat(eventService.getAllPeriodicEventsByDateIntervals(START, END))
        .singleElement()
        .extracting(PeriodicEvents::getNoHelmet)
        .isEqualTo(2);
  }

  @Test
  @DisplayName("periodic: truncation is per event, so N windows lose up to N seconds in total")
  void periodic_truncationErrorCompoundsPerEvent() {
    // Three 999 ms windows are 2.997 s of real exposure and are reported as 0. Summing the
    // milliseconds first and dividing once would report 2. This pins the per-event choice, which
    // matches what the endpoint did before the unit change and keeps the chart's shape stable.
    stubPeriodic(
        periodic(EventNameEnum.NO_JACKET, utc(2023, 11, 14, 8, 0), "999"),
        periodic(EventNameEnum.NO_JACKET, utc(2023, 11, 14, 9, 0), "999"),
        periodic(EventNameEnum.NO_JACKET, utc(2023, 11, 14, 10, 0), "999"));

    assertThat(eventService.getAllPeriodicEventsByDateIntervals(START, END))
        .singleElement()
        .extracting(PeriodicEvents::getNoJacket)
        .isEqualTo(0);
  }

  @Test
  @DisplayName("periodic: the response is SECONDS, so a 6500 ms violation is 6 - not 6500")
  void periodic_responseStaysInSecondsSoTheChartDoesNotGrow1000x() {
    // The dashboard plots noHelmet/noJacket raw (web/src/pages/ChartsContainer.js). Returning the
    // stored milliseconds would make every periodic chart 1000x taller overnight with no code
    // change on the frontend and no error anywhere.
    stubPeriodic(periodic(EventNameEnum.NO_JACKET, utc(2023, 11, 14, 8, 0), "6500"));

    assertThat(eventService.getAllPeriodicEventsByDateIntervals(START, END))
        .singleElement()
        .extracting(PeriodicEvents::getNoJacket)
        .isEqualTo(6);
  }

  @Test
  @DisplayName("periodic: a duration beyond int milliseconds still reports the right seconds")
  void periodic_durationBeyondIntMillisecondsIsNotTruncatedByIntValue() {
    // 3_000_000_000 ms is ~34.7 days. The old code called intValue() on the stored BigDecimal,
    // which returns the low-order 32 bits; the seconds value (3_000_000) fits an int comfortably,
    // but only if the division happens on the BigDecimal rather than after a wrapped intValue().
    stubPeriodic(periodic(EventNameEnum.NO_HELMET, utc(2023, 11, 14, 8, 0), "3000000000"));

    assertThat(eventService.getAllPeriodicEventsByDateIntervals(START, END))
        .singleElement()
        .extracting(PeriodicEvents::getNoHelmet)
        .isEqualTo(3_000_000);
  }

  @Test
  @DisplayName("periodic: output is NOT sorted - it follows first-appearance order of the input")
  void periodic_outputIsNotSorted() {
    // Determined from the code: calculatePeriodicEvents appends a new PeriodicEvents the first
    // time it sees a day and never sorts the list. In production the ordering only looks
    // ascending because the repository method is ...OrderByStartTimeAsc; the service itself
    // guarantees nothing.
    stubPeriodic(
        periodic(EventNameEnum.NO_HELMET, utc(2023, 12, 25, 8, 0), "4"),
        periodic(EventNameEnum.NO_HELMET, utc(2023, 11, 14, 8, 0), "6"),
        periodic(EventNameEnum.NO_JACKET, utc(2023, 12, 25, 9, 0), "2"));

    List<PeriodicEvents> result = eventService.getAllPeriodicEventsByDateIntervals(START, END);

    assertThat(result).extracting(PeriodicEvents::getDate)
        .containsExactly("25.12.2023", "14.11.2023");
  }

  @Test
  @DisplayName("periodic: buckets the day in HARD-WIRED UTC, diverging from the countable endpoint")
  void periodic_bucketsDayInUtcAndDivergesFromCountable() {
    TimeZone.setDefault(TimeZone.getTimeZone("America/New_York"));
    long instant = utc(2023, 11, 14, 2, 0); // = 2023-11-13 21:00 in New York

    when(eventRepository.findAllByEventTypeInAndStartTimeBetweenOrderByStartTimeAsc(
        eq(PERIODIC_TYPES), eq(START), eq(END)))
        .thenReturn(List.of(periodic(EventNameEnum.NO_HELMET, instant, "9")));
    when(eventRepository.findAllByEventTypeInAndStartTimeBetweenOrderByStartTimeAsc(
        eq(COUNTABLE_TYPES), eq(START), eq(END)))
        .thenReturn(List.of(countable(EventNameEnum.FALL, instant)));

    List<PeriodicEvents> periodicResult =
        eventService.getAllPeriodicEventsByDateIntervals(START, END);
    List<CountableEvents> countableResult =
        eventService.getAllCountableEventsByDateIntervals(START, END);

    // Same instant, two different days: the chart families disagree. A later slice unifies them.
    assertThat(periodicResult).singleElement()
        .extracting(PeriodicEvents::getDate).isEqualTo("14.11.2023");
    assertThat(countableResult).singleElement()
        .extracting(CountableEvents::getDate).isEqualTo("13.11.2023");
  }

  @Test
  @DisplayName("periodic: no matching events -> empty list")
  void periodic_noEventsReturnsEmptyList() {
    stubPeriodic();

    assertThat(eventService.getAllPeriodicEventsByDateIntervals(START, END)).isEmpty();
  }

  @Test
  @DisplayName("periodic: queries the repository with exactly [NO_HELMET, NO_JACKET]")
  void periodic_queriesOnlyPeriodicTypes() {
    stubPeriodic();

    eventService.getAllPeriodicEventsByDateIntervals(START, END);

    verify(eventRepository).findAllByEventTypeInAndStartTimeBetweenOrderByStartTimeAsc(
        eventTypesCaptor.capture(), eq(START), eq(END));
    assertThat(eventTypesCaptor.getValue()).containsExactly("NO_HELMET", "NO_JACKET");
  }

  // ---------------------------------------------------------------------------------------------
  // getAllEvents / getAllEventsByDateIntervals / deletePeriodicEventById
  // ---------------------------------------------------------------------------------------------

  /**
   * THE ASSERTION THIS REPLACES was {@code assertThat(eventService.getAllEvents()).isSameAs(all)}
   * - straight delegation, the repository's entities handed to the client untouched. It had to
   * change because it pinned the second half of the millisecond leak: {@code /event/all-events}
   * served {@code Event} documents, whose {@code timePeriod} is milliseconds, into a grid column
   * headed "Time Period" that the rest of the API expresses in seconds.
   */
  @Test
  @DisplayName("getAllEvents: maps to EventResponseDto and converts timePeriod ms -> SECONDS")
  void getAllEvents_mapsToResponseDtoInSeconds() {
    Event periodic = periodic(EventNameEnum.NO_HELMET, utc(2023, 11, 14, 8, 0), "5000");
    periodic.setCameraName("Camera7");
    periodic.setEndTime(utc(2023, 11, 14, 8, 5));
    when(eventRepository.findAll()).thenReturn(List.of(periodic));

    List<EventResponseDto> result = eventService.getAllEvents();

    assertThat(result).singleElement().satisfies(dto -> {
      assertThat(dto.getTimePeriod()).isEqualTo(5);
      assertThat(dto.getId()).isEqualTo(periodic.getId());
      assertThat(dto.getEventType()).isEqualTo("NO_HELMET");
      assertThat(dto.getCameraName()).isEqualTo("Camera7");
      assertThat(dto.getStartTime()).isEqualTo(periodic.getStartTime());
      assertThat(dto.getEndTime()).isEqualTo(periodic.getEndTime());
      assertThat(dto.getConfidencePercentage()).isEqualByComparingTo(BigDecimal.valueOf(90));
    });
  }

  @Test
  @DisplayName("getAllEvents: a countable event's timePeriod stays NULL - not 0")
  void getAllEvents_nullTimePeriodStaysNull() {
    // The grid renders `row.timePeriod === null ? '-' : row.timePeriod`. A 0 would claim a
    // zero-second violation for an event type that never carries a duration.
    when(eventRepository.findAll())
        .thenReturn(List.of(countable(EventNameEnum.FALL, utc(2023, 11, 14, 8, 0))));

    assertThat(eventService.getAllEvents()).singleElement()
        .extracting(EventResponseDto::getTimePeriod)
        .isNull();
  }

  @Test
  @DisplayName("getAllEvents: truncates per event, exactly as the periodic chart does")
  void getAllEvents_truncatesPerEventLikeTheChart() {
    // Same rounding rule as calculatePeriodicEvents, so the grid and the chart cannot disagree
    // about the same event: 5900 ms is 5 s in both.
    when(eventRepository.findAll()).thenReturn(List.of(
        periodic(EventNameEnum.NO_HELMET, utc(2023, 11, 14, 8, 0), "5900"),
        periodic(EventNameEnum.NO_JACKET, utc(2023, 11, 14, 9, 0), "2999"),
        periodic(EventNameEnum.NO_JACKET, utc(2023, 11, 14, 10, 0), "999")));

    assertThat(eventService.getAllEvents()).extracting(EventResponseDto::getTimePeriod)
        .containsExactly(5, 2, 0);
  }

  @Test
  @DisplayName("getAllEvents: the payload does NOT carry schemaVersion or isProcessed")
  void getAllEvents_doesNotLeakStorageFields() throws Exception {
    // schemaVersion records which unit the STORED value is in. Once the DTO has converted to
    // seconds, shipping it alongside would assert that the number is milliseconds - the payload
    // would contradict itself. isProcessed is an ingest flag no consumer reads.
    Event stored = periodic(EventNameEnum.NO_HELMET, utc(2023, 11, 14, 8, 0), "5000");
    stored.setSchemaVersion(Event.SCHEMA_VERSION_MILLIS);
    stored.setIsProcessed("false");
    when(eventRepository.findAll()).thenReturn(List.of(stored));

    String json = new ObjectMapper()
        .writeValueAsString(eventService.getAllEvents().get(0));

    assertThat(json).doesNotContain("schemaVersion");
    assertThat(json).doesNotContain("isProcessed");
    // ...and timePeriod is present as an explicit key, because `row.timePeriod === null` in the
    // grid is a strict comparison that an absent key would fail.
    assertThat(json).contains("\"timePeriod\":5");
  }

  @Test
  @DisplayName("getAllEvents: a null timePeriod serialises as an explicit JSON null, not an absent key")
  void getAllEvents_nullTimePeriodSerialisesAsExplicitNull() throws Exception {
    when(eventRepository.findAll())
        .thenReturn(List.of(countable(EventNameEnum.FALL, utc(2023, 11, 14, 8, 0))));

    String json = new ObjectMapper().writeValueAsString(eventService.getAllEvents().get(0));

    assertThat(json).contains("\"timePeriod\":null");
  }

  @Test
  @DisplayName("getAllEventsByDateIntervals: queries all five types, in enum-ish declaration order")
  void getAllEventsByDateIntervals_queriesAllFiveTypes() {
    when(eventRepository.findAllByEventTypeInAndStartTimeBetweenOrderByStartTimeAsc(
        eq(ALL_TYPES), eq(START), eq(END))).thenReturn(List.of());

    eventService.getAllEventsByDateIntervals(START, END);

    verify(eventRepository).findAllByEventTypeInAndStartTimeBetweenOrderByStartTimeAsc(
        eventTypesCaptor.capture(), eq(START), eq(END));
    assertThat(eventTypesCaptor.getValue())
        .containsExactly("FALL", "ARMS_UP", "FRONT_BEND", "NO_HELMET", "NO_JACKET");
  }

  @Test
  @DisplayName("delete: unknown id throws EntityNotFoundException whose message names the EVENT")
  void delete_unknownId_throwsEntityNotFoundWithEventWording() {
    when(eventRepository.findById("evt-404")).thenReturn(Optional.empty());

    // This assertion used to read "User Not Found: evt-404": the service reused
    // USER_NOT_FOUND_MESSAGE for an Event lookup, so deleting a row from the events grid told the
    // client - and the operator reading the toast - that a USER did not exist. The id in the
    // message is an event id, so the two together are actively misleading: they invite someone to
    // go looking in the wrong collection.
    assertThatThrownBy(() -> eventService.deletePeriodicEventById("evt-404"))
        .isInstanceOf(EntityNotFoundException.class)
        .hasMessage("Event Not Found: evt-404");

    verify(eventRepository, never()).deleteById("evt-404");
  }

  @Test
  @DisplayName("delete: existing id is looked up first, then deleted")
  void delete_existingId_deletes() {
    when(eventRepository.findById("evt-1"))
        .thenReturn(Optional.of(countable(EventNameEnum.FALL, utc(2023, 11, 14, 8, 0))));

    eventService.deletePeriodicEventById("evt-1");

    verify(eventRepository).deleteById("evt-1");
  }

  // ---------------------------------------------------------------------------------------------
  // generateEventsPdf - only the envelope is pinned; iText embeds a creation timestamp, so the
  // bytes themselves are not stable and are deliberately NOT snapshotted.
  // ---------------------------------------------------------------------------------------------

  @Test
  @DisplayName("pdf: happy path emits a complete PDF (%PDF- header, %%EOF trailer)")
  void pdf_happyPathEmitsCompletePdf() {
    List<Event> events = List.of(
        countable(EventNameEnum.FALL, utc(2023, 11, 14, 8, 0)),
        periodic(EventNameEnum.NO_HELMET, utc(2023, 11, 14, 9, 0), "5"));

    ByteArrayOutputStream out = eventService.generateEventsPdf(events, START, END);
    String asLatin1 = new String(out.toByteArray(), StandardCharsets.ISO_8859_1);

    assertThat(asLatin1).startsWith("%PDF-");
    assertThat(asLatin1).contains("%%EOF");
  }

  @Test
  @DisplayName("pdf: an empty event list still emits a valid (header-only-table) PDF")
  void pdf_emptyEventListStillEmitsPdf() {
    ByteArrayOutputStream out = eventService.generateEventsPdf(List.of(), START, END);

    assertThat(new String(out.toByteArray(), StandardCharsets.ISO_8859_1)).startsWith("%PDF-");
  }

  @Test
  @DisplayName("pdf: a bad event THROWS ReportGenerationException instead of returning 0 bytes")
  void pdf_brokenEventThrowsReportGenerationException() {
    // startTime == null makes getFormattedDateTime NPE inside the try block.
    //
    // THIS ASSERTION IS THE INVERSE OF THE ONE IT REPLACES. The old test pinned the defect: it
    // asserted .doesNotThrowAnyException() and that the returned stream was EMPTY. iText buffers
    // the document until close(), which the error path never reached, so the caller received zero
    // bytes and no signal - EventController.sendPdfEmail mailed them and replied
    // "Email sent successfully!". A caller that cannot distinguish a report from no report cannot
    // tell the truth to the user, so the swallow is the defect and returning normally is the
    // behaviour that had to go.
    Event broken = Event.builder().eventType(EventNameEnum.FALL.name()).startTime(null).build();

    assertThatThrownBy(() -> eventService.generateEventsPdf(List.of(broken), START, END))
        .isInstanceOf(ReportGenerationException.class)
        .hasMessageContaining("Failed to generate the events PDF")
        // The cause is kept: the stack trace that used to go to stdout is now attached to the
        // exception the caller sees, so nothing that was diagnosable before is lost.
        .hasCauseInstanceOf(NullPointerException.class);
  }

  @Test
  @DisplayName("pdf: the Details column prints SECONDS, not the stored milliseconds")
  void pdf_periodicDurationIsPrintedInSeconds() throws Exception {
    // The emailed report was the other place the storage unit leaked: it printed
    // event.getTimePeriod() verbatim, so a 5-second violation read "Time Period: 5000" while the
    // dashboard next to it said 5.
    List<Event> events = List.of(
        periodic(EventNameEnum.NO_HELMET, utc(2023, 11, 14, 9, 0), "5000"),
        periodic(EventNameEnum.NO_JACKET, utc(2023, 11, 14, 10, 0), "2999"));

    String text = pdfTextOf(eventService.generateEventsPdf(events, START, END));

    assertThat(text).contains("Time Period: 5 s");
    // Truncated per event, the same rule as the periodic chart and the events grid.
    assertThat(text).contains("Time Period: 2 s");
    assertThat(text).doesNotContain("5000");
    assertThat(text).doesNotContain("2999");
  }

  @Test
  @DisplayName("pdf: a countable event has no Details cell at all - no bogus 0")
  void pdf_countableEventHasNoDuration() {
    String text = pdfTextOf(eventService.generateEventsPdf(
        List.of(countable(EventNameEnum.FALL, utc(2023, 11, 14, 8, 0))), START, END));

    assertThat(text).contains("FALL");
    assertThat(text).doesNotContain("Time Period:");
  }

  @Test
  @DisplayName("pdf: a stream is never returned empty - success implies bytes")
  void pdf_successAlwaysImpliesNonEmptyBytes() {
    // The contract EventController relies on: generateEventsPdf either returns a real PDF or
    // throws. There is no third outcome, and this is the assertion that says so for the two
    // inputs that do succeed.
    assertThat(eventService.generateEventsPdf(List.of(), START, END).toByteArray()).isNotEmpty();
    assertThat(eventService.generateEventsPdf(
        List.of(countable(EventNameEnum.FALL, utc(2023, 11, 14, 8, 0))), START, END)
        .toByteArray()).isNotEmpty();
  }

  // ---------------------------------------------------------------------------------------------
  // helpers
  // ---------------------------------------------------------------------------------------------

  private void stubCountable(Event... events) {
    when(eventRepository.findAllByEventTypeInAndStartTimeBetweenOrderByStartTimeAsc(
        eq(COUNTABLE_TYPES), eq(START), eq(END))).thenReturn(Arrays.asList(events));
  }

  private void stubPeriodic(Event... events) {
    when(eventRepository.findAllByEventTypeInAndStartTimeBetweenOrderByStartTimeAsc(
        eq(PERIODIC_TYPES), eq(START), eq(END))).thenReturn(Arrays.asList(events));
  }

  private static long utc(int year, int month, int day, int hour, int minute) {
    return LocalDateTime.of(year, month, day, hour, minute).toInstant(ZoneOffset.UTC).toEpochMilli();
  }

  private static Event countable(EventNameEnum type, long startTime) {
    return Event.builder()
        .id(type.name() + "-" + startTime)
        .eventType(type.name())
        .cameraName("Camera1")
        .confidencePercentage(BigDecimal.valueOf(90))
        .startTime(startTime)
        .build();
  }

  private static Event periodic(EventNameEnum type, long startTime, String timePeriod) {
    Event event = countable(type, startTime);
    event.setTimePeriod(new BigDecimal(timePeriod));
    return event;
  }

  /**
   * Reads the text back out of a generated PDF. iText embeds a creation timestamp, so the bytes
   * are not stable and cannot be snapshotted - but the rendered text is, and it is the only way
   * to assert what the operator actually reads in the emailed report.
   */
  private static String pdfTextOf(ByteArrayOutputStream pdf) {
    try {
      PdfReader reader = new PdfReader(pdf.toByteArray());
      StringBuilder text = new StringBuilder();
      for (int page = 1; page <= reader.getNumberOfPages(); page++) {
        text.append(PdfTextExtractor.getTextFromPage(reader, page));
      }
      reader.close();
      return text.toString();
    } catch (Exception e) {
      throw new IllegalStateException("could not read the generated PDF back", e);
    }
  }
}
