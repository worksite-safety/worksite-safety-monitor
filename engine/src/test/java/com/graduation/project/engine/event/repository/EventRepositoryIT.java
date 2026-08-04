package com.graduation.project.engine.event.repository;

import static org.assertj.core.api.Assertions.assertThat;

import com.graduation.project.engine.AbstractIntegrationTest;
import com.graduation.project.engine.event.model.Event;
import com.graduation.project.engine.event.model.EventNameEnum;
import java.math.BigDecimal;
import java.util.List;
import org.bson.Document;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.DisplayName;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.data.mongodb.core.MongoTemplate;

/**
 * Characterisation tests for how {@code Event} is actually stored in, and read back from,
 * MongoDB. Both tests are probe-then-pin: they were written by observing the real behaviour of
 * Spring Data MongoDB 4.0.3 / mongodb-driver-sync 4.8.2 against a real server, and they now pin
 * it so the upcoming Boot 3.0.4 -> 3.5.x upgrade cannot change it silently.
 */
class EventRepositoryIT extends AbstractIntegrationTest {

  private static final String COLLECTION = "event";

  @Autowired
  private EventRepository eventRepository;

  @Autowired
  private MongoTemplate mongoTemplate;

  @BeforeEach
  void clearCollection() {
    mongoTemplate.getCollection(COLLECTION).deleteMany(new Document());
  }

  /**
   * WHAT BSON TYPE IS {@code Event.timePeriod}?
   *
   * <p>The Java field is a {@link BigDecimal}. Spring Data MongoDB has historically mapped
   * BigDecimal to a BSON <em>String</em> and only later moved towards Decimal128
   * ({@code MongoCustomConversions.BigDecimalRepresentation}, Spring Data MongoDB 4.2+). Which
   * of the two applies here is not academic: a later migration multiplies every stored duration
   * by 1000, and the query is a different query depending on the answer.
   *
   * <ul>
   *   <li>Decimal128 -> {@code db.event.updateMany({}, [{$mul: {timePeriod: 1000}}])} works.</li>
   *   <li>String -> {@code $mul} fails; the migration needs an aggregation pipeline that runs
   *       {@code $toDecimal} first, e.g.
   *       {@code [{$set: {timePeriod: {$toString: {$multiply: [{$toDecimal: "$timePeriod"}, 1000]}}}}]}.</li>
   * </ul>
   *
   * <p>It is also the most dangerous silent change in the upcoming upgrade: if new writes become
   * Decimal128 while old documents stay String, every range query and every arithmetic
   * aggregation over the field starts disagreeing with itself. String comparison also means
   * {@code "10" < "9"}, so a mixed collection is not merely inconsistent, it is wrong.
   */
  @Test
  @DisplayName("timePeriod (BigDecimal) is persisted as a BSON String, not Decimal128")
  void timePeriodIsStoredAsBsonString() {
    eventRepository.save(Event.builder()
        .cameraName("Camera1")
        .confidencePercentage(new BigDecimal("90"))
        .eventType(EventNameEnum.NO_HELMET.name())
        .isProcessed("false")
        .timePeriod(new BigDecimal("5"))
        .startTime(1_700_000_000_000L)
        .endTime(1_700_000_005_000L)
        .build());

    Document raw = mongoTemplate.getCollection(COLLECTION).find().first();

    assertThat(raw).isNotNull();
    System.out.println("[EventRepositoryIT] raw BSON document = " + raw.toJson());
    raw.forEach((key, value) -> System.out.printf(
        "[EventRepositoryIT]   %-21s -> %-8s (%s)%n",
        key, value, value == null ? "null" : value.getClass().getName()));

    Object timePeriod = raw.get("timePeriod");

    // THE ANSWER: java.lang.String, i.e. BSON string "5".
    assertThat(timePeriod).isInstanceOf(String.class);
    assertThat(timePeriod).isEqualTo("5");
    assertThat(timePeriod).isNotInstanceOf(org.bson.types.Decimal128.class);

    // confidencePercentage is a BigDecimal too and shares the fate of timePeriod - any
    // migration has to consider both.
    assertThat(raw.get("confidencePercentage")).isInstanceOf(String.class);

    // startTime is a Long and lands as a BSON 64-bit int, which is why the Between query below
    // compares numerically rather than lexicographically.
    assertThat(raw.get("startTime")).isInstanceOf(Long.class);

    // Round-tripping through the repository hides all of this: the read converts back to
    // BigDecimal, so no unit test that goes through the mapper could ever have caught it.
    Event reloaded = eventRepository.findAll().get(0);
    assertThat(reloaded.getTimePeriod()).isEqualByComparingTo(new BigDecimal("5"));
  }

  /**
   * IS THE DATE RANGE INCLUSIVE?
   *
   * <p>{@code findAllByEventTypeInAndStartTimeBetweenOrderByStartTimeAsc} is the single query
   * behind every date-range endpoint in this application: the countable chart, the pie chart,
   * the periodic chart, the events grid and the PDF report all funnel through
   * {@code EventService.getAllEventsByEventTypes}.
   *
   * <p>HISTORY - THIS ASSERTION USED TO SAY THE OPPOSITE. The method was a DERIVED query whose
   * name contained {@code Between}, and Spring Data MongoDB's query creator maps {@code BETWEEN}
   * to {@code $gt}/{@code $lt} - exclusive at BOTH ends, the opposite of JPA. This test measured
   * that and pinned it: an event whose {@code startTime} equalled the requested {@code startDate}
   * or {@code endDate} to the millisecond was dropped, from every chart, silently. The UI sends
   * day boundaries, so it lost events at exactly midnight.
   *
   * <p>The repository now declares the range explicitly with {@code $gte}/{@code $lte} (see
   * {@code EventRepository}), so a requested range means the closed interval a user reading
   * "14.11.2023 - 15.11.2023" would expect. This test is the inversion of the old one and is the
   * reason the fix cannot regress: nothing else in the stack can observe the operators.
   */
  @Test
  @DisplayName("the date range is INCLUSIVE at both ends: events exactly on the boundaries are kept")
  void rangeIsInclusiveAtBothEnds() {
    long startDate = 1_700_000_000_000L;
    long endDate = startDate + 86_400_000L;

    saveFallAt("at-start", startDate);
    saveFallAt("just-after-start", startDate + 1);
    saveFallAt("just-before-end", endDate - 1);
    saveFallAt("at-end", endDate);

    List<Event> found = eventRepository.findAllByEventTypeInAndStartTimeBetweenOrderByStartTimeAsc(
        List.of(EventNameEnum.FALL.name()), startDate, endDate);

    System.out.println("[EventRepositoryIT] range(" + startDate + ", " + endDate + ") returned "
        + found.stream().map(Event::getCameraName).toList());

    assertThat(found).extracting(Event::getCameraName)
        .containsExactly("at-start", "just-after-start", "just-before-end", "at-end");
    assertThat(found).hasSize(4);
  }

  /**
   * Widening the bounds by one millisecond was the WORKAROUND for the exclusive range. It still
   * returns everything, of course - but it must no longer be necessary, and the second assertion
   * is what says so: the widened result and the exact result are now the same list.
   *
   * <p>Kept rather than deleted because a caller somewhere may still be widening out of habit,
   * and this pins that doing so is now a no-op rather than a silent one-millisecond overreach.
   */
  @Test
  @DisplayName("widening the bounds by 1 ms is now redundant, not required")
  void wideningTheBoundsByOneMillisecondIsNowRedundant() {
    long startDate = 1_700_000_000_000L;
    long endDate = startDate + 86_400_000L;

    saveFallAt("at-start", startDate);
    saveFallAt("just-after-start", startDate + 1);
    saveFallAt("just-before-end", endDate - 1);
    saveFallAt("at-end", endDate);

    List<Event> widened = eventRepository.findAllByEventTypeInAndStartTimeBetweenOrderByStartTimeAsc(
        List.of(EventNameEnum.FALL.name()), startDate - 1, endDate + 1);
    List<Event> exact = eventRepository.findAllByEventTypeInAndStartTimeBetweenOrderByStartTimeAsc(
        List.of(EventNameEnum.FALL.name()), startDate, endDate);

    assertThat(widened).extracting(Event::getCameraName)
        .containsExactly("at-start", "just-after-start", "just-before-end", "at-end");
    assertThat(exact).extracting(Event::getCameraName)
        .isEqualTo(widened.stream().map(Event::getCameraName).toList());
  }

  /**
   * Pins the OPERATORS rather than just the outcome, by running the two candidate raw queries
   * side by side. The repository method must agree with {@code $gte}/{@code $lte} and disagree
   * with {@code $gt}/{@code $lt}; if the declaration is ever reverted to a derived
   * {@code ...Between...} name, this fails loudly instead of merely changing a count somewhere in
   * a chart.
   *
   * <p>This assertion was previously the exact inverse ({@code derived == exclusive},
   * {@code derived != inclusive}) - it is the second place the old exclusive behaviour was pinned.
   */
  @Test
  @DisplayName("the range query matches raw $gte/$lte and NOT raw $gt/$lt")
  void rangeQueryMatchesGteLteNotGtLt() {
    long startDate = 1_700_000_000_000L;
    long endDate = startDate + 86_400_000L;

    saveFallAt("at-start", startDate);
    saveFallAt("just-after-start", startDate + 1);
    saveFallAt("just-before-end", endDate - 1);
    saveFallAt("at-end", endDate);

    List<String> derived =
        eventRepository.findAllByEventTypeInAndStartTimeBetweenOrderByStartTimeAsc(
                List.of(EventNameEnum.FALL.name()), startDate, endDate)
            .stream().map(Event::getCameraName).toList();

    List<String> exclusive = rawStartTimeQuery("$gt", startDate, "$lt", endDate);
    List<String> inclusive = rawStartTimeQuery("$gte", startDate, "$lte", endDate);

    System.out.println("[EventRepositoryIT] repository = " + derived);
    System.out.println("[EventRepositoryIT] $gt/$lt    = " + exclusive);
    System.out.println("[EventRepositoryIT] $gte/$lte  = " + inclusive);

    assertThat(derived).isEqualTo(inclusive);
    assertThat(derived).isNotEqualTo(exclusive);
    assertThat(inclusive).hasSize(4);
  }

  /**
   * The ordering contract, asserted independently of the range. The method name still ends in
   * {@code OrderByStartTimeAsc} but the sort no longer comes from the derived name - it is
   * declared on the {@code @Query} - so it needs its own test rather than riding on the range
   * tests' {@code containsExactly}.
   */
  @Test
  @DisplayName("results are still sorted by startTime ascending, from the @Query sort")
  void resultsAreSortedByStartTimeAscending() {
    long base = 1_700_000_000_000L;

    saveFallAt("third", base + 3000);
    saveFallAt("first", base + 1000);
    saveFallAt("fourth", base + 4000);
    saveFallAt("second", base + 2000);

    List<Event> found = eventRepository.findAllByEventTypeInAndStartTimeBetweenOrderByStartTimeAsc(
        List.of(EventNameEnum.FALL.name()), base, base + 10_000);

    assertThat(found).extracting(Event::getCameraName)
        .containsExactly("first", "second", "third", "fourth");
  }

  /**
   * The {@code eventType $in} half of the filter, which the {@code @Query} now spells out by hand.
   * Without this, a typo in the JSON string that dropped the type filter entirely would still pass
   * every other test in this class, because they only ever save FALL documents.
   */
  @Test
  @DisplayName("the eventType $in filter still excludes types that were not asked for")
  void eventTypeFilterStillApplies() {
    long base = 1_700_000_000_000L;

    saveFallAt("a-fall", base + 1000);
    eventRepository.save(Event.builder()
        .cameraName("a-no-helmet")
        .confidencePercentage(new BigDecimal("90"))
        .eventType(EventNameEnum.NO_HELMET.name())
        .isProcessed("false")
        .timePeriod(new BigDecimal("5000"))
        .startTime(base + 2000)
        .endTime(base + 2000)
        .build());

    assertThat(eventRepository.findAllByEventTypeInAndStartTimeBetweenOrderByStartTimeAsc(
        List.of(EventNameEnum.FALL.name()), base, base + 10_000))
        .extracting(Event::getCameraName).containsExactly("a-fall");

    assertThat(eventRepository.findAllByEventTypeInAndStartTimeBetweenOrderByStartTimeAsc(
        List.of(EventNameEnum.FALL.name(), EventNameEnum.NO_HELMET.name()), base, base + 10_000))
        .extracting(Event::getCameraName).containsExactly("a-fall", "a-no-helmet");
  }

  private List<String> rawStartTimeQuery(String lowerOperator, long lower, String upperOperator,
      long upper) {
    return mongoTemplate.getCollection(COLLECTION)
        .find(new Document("startTime",
            new Document(lowerOperator, lower).append(upperOperator, upper)))
        .sort(new Document("startTime", 1))
        .map(document -> document.getString("cameraName"))
        .into(new java.util.ArrayList<>());
  }

  private void saveFallAt(String label, long startTime) {
    eventRepository.save(Event.builder()
        .cameraName(label)
        .confidencePercentage(new BigDecimal("90"))
        .eventType(EventNameEnum.FALL.name())
        .isProcessed("false")
        .startTime(startTime)
        .endTime(startTime)
        .build());
  }
}
