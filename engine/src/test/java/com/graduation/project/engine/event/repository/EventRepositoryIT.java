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
   * IS {@code Between} INCLUSIVE?
   *
   * <p>{@code findAllByEventTypeInAndStartTimeBetweenOrderByStartTimeAsc} is the single query
   * behind every date-range endpoint in this application: the countable chart, the pie chart,
   * the periodic chart, the events grid and the PDF report all funnel through
   * {@code EventService.getAllEventsByEventTypes}.
   *
   * <p>Spring Data MongoDB's query creator maps {@code BETWEEN} to {@code $gt}/{@code $lt} -
   * exclusive at BOTH ends. This is the opposite of JPA, where {@code Between} is inclusive, and
   * it is the kind of difference that survives a framework upgrade unnoticed because nothing
   * fails; the numbers are just quietly a little too small.
   *
   * <p>Consequence for the dashboard: an event whose {@code startTime} equals the requested
   * {@code startDate} or {@code endDate} to the millisecond is dropped. The UI sends day
   * boundaries, so in practice this loses events at exactly midnight - rare, but silent, and
   * every chart inherits it.
   */
  @Test
  @DisplayName("Between is EXCLUSIVE at both ends: events exactly on the boundaries are dropped")
  void betweenIsExclusiveAtBothEnds() {
    long startDate = 1_700_000_000_000L;
    long endDate = startDate + 86_400_000L;

    saveFallAt("at-start", startDate);
    saveFallAt("just-after-start", startDate + 1);
    saveFallAt("just-before-end", endDate - 1);
    saveFallAt("at-end", endDate);

    List<Event> found = eventRepository.findAllByEventTypeInAndStartTimeBetweenOrderByStartTimeAsc(
        List.of(EventNameEnum.FALL.name()), startDate, endDate);

    System.out.println("[EventRepositoryIT] Between(" + startDate + ", " + endDate + ") returned "
        + found.stream().map(Event::getCameraName).toList());

    assertThat(found).extracting(Event::getCameraName)
        .containsExactly("just-after-start", "just-before-end");

    assertThat(found).extracting(Event::getCameraName)
        .doesNotContain("at-start", "at-end");
    assertThat(found).hasSize(2);
  }

  /**
   * The same fact stated from the other side, so the intent survives a careless "fix" of the
   * test above: a caller who wants an inclusive range must widen the bounds by one millisecond.
   * That is the workaround any migration or endpoint change should use until the repository
   * method itself is changed to explicit {@code $gte}/{@code $lte}.
   */
  @Test
  @DisplayName("widening the bounds by 1 ms is what makes the range inclusive")
  void wideningTheBoundsByOneMillisecondIncludesTheBoundaries() {
    long startDate = 1_700_000_000_000L;
    long endDate = startDate + 86_400_000L;

    saveFallAt("at-start", startDate);
    saveFallAt("just-after-start", startDate + 1);
    saveFallAt("just-before-end", endDate - 1);
    saveFallAt("at-end", endDate);

    List<Event> found = eventRepository.findAllByEventTypeInAndStartTimeBetweenOrderByStartTimeAsc(
        List.of(EventNameEnum.FALL.name()), startDate - 1, endDate + 1);

    assertThat(found).extracting(Event::getCameraName)
        .containsExactly("at-start", "just-after-start", "just-before-end", "at-end");
  }

  /**
   * Pins the operators rather than just the outcome, by running the two candidate raw queries
   * side by side. The derived method must agree with {@code $gt}/{@code $lt} and disagree with
   * {@code $gte}/{@code $lte}; if a future Spring Data version switches, this fails loudly
   * instead of merely changing a count somewhere in a chart.
   */
  @Test
  @DisplayName("the derived Between matches raw $gt/$lt and NOT raw $gte/$lte")
  void derivedBetweenMatchesGtLtNotGteLte() {
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

    System.out.println("[EventRepositoryIT] derived  = " + derived);
    System.out.println("[EventRepositoryIT] $gt/$lt  = " + exclusive);
    System.out.println("[EventRepositoryIT] $gte/$lte= " + inclusive);

    assertThat(derived).isEqualTo(exclusive);
    assertThat(derived).isNotEqualTo(inclusive);
    assertThat(inclusive).hasSize(4);
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
