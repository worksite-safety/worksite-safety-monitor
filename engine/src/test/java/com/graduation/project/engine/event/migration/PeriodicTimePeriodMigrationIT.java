package com.graduation.project.engine.event.migration;

import static org.assertj.core.api.Assertions.assertThat;

import com.graduation.project.engine.AbstractIntegrationTest;
import com.graduation.project.engine.event.model.Event;
import com.graduation.project.engine.event.model.EventNameEnum;
import com.graduation.project.engine.event.repository.EventRepository;
import java.math.BigDecimal;
import java.util.ArrayList;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import org.bson.Document;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.DisplayName;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.context.ApplicationContext;
import org.springframework.data.mongodb.core.MongoTemplate;

/**
 * Drives {@link PeriodicTimePeriodMigration} against a real MongoDB.
 *
 * <h2>Why this cannot be a unit test</h2>
 *
 * <p>The migration is an aggregation-pipeline update. Its entire content - {@code $toDecimal},
 * {@code $multiply}, {@code $toString}, {@code $unset} - is executed by the server, not by any
 * Java the JVM could stub. A mock of {@code MongoTemplate} would assert that the pipeline equals
 * a pipeline this test also wrote, which proves only that two copies of the same guess agree.
 *
 * <p>The pipeline is also not free to be anything: {@code Event.timePeriod} is a
 * {@link BigDecimal} that Spring Data MongoDB 4.0.3 persists as a BSON <em>String</em>, pinned by
 * {@code EventRepositoryIT#timePeriodIsStoredAsBsonString}. A {@code $mul} update cannot multiply
 * a string, and {@code $toDouble} would round-trip 5 -> "5000.0000000000001"-class artifacts into
 * a field whose whole point is exactness. Only the server can settle which pipeline actually
 * produces the intended bytes.
 *
 * <h2>The fixture</h2>
 *
 * <p>Documents are inserted as raw {@link Document}s, in exactly the shape
 * {@code EventRepositoryIT} observed the mapper produce, rather than through the repository. That
 * is what makes byte-identity assertions meaningful: nothing in this test can accidentally write
 * a {@code schemaVersion} the migration then claims credit for skipping.
 */
class PeriodicTimePeriodMigrationIT extends AbstractIntegrationTest {

  private static final String COLLECTION = "event";

  private static final long START_TIME = 1_700_000_000_000L;

  @Autowired
  private MongoTemplate mongoTemplate;

  @Autowired
  private EventRepository eventRepository;

  @Autowired
  private ApplicationContext applicationContext;

  private PeriodicTimePeriodMigration migration;

  @BeforeEach
  void setUp() {
    mongoTemplate.getCollection(COLLECTION).deleteMany(new Document());
    // Constructed by hand: the bean is @ConditionalOnProperty and is absent from this context by
    // design - see runnerIsNotRegisteredUnlessExplicitlyEnabled().
    migration = new PeriodicTimePeriodMigration(mongoTemplate);
  }

  /**
   * The guard, asserted rather than assumed. A migration that performs a destructive in-place
   * update must not be one restart away from running; it has to be something an operator turns on
   * for exactly one boot.
   */
  @Test
  @DisplayName("the ApplicationRunner is NOT in the context unless the property is explicitly true")
  void runnerIsNotRegisteredUnlessExplicitlyEnabled() {
    assertThat(applicationContext.getBeanNamesForType(PeriodicTimePeriodMigration.class))
        .as("event.migration.periodic-to-millis.enabled defaults to false")
        .isEmpty();
  }

  @Test
  @DisplayName("up(): seconds-valued periodic documents are multiplied by 1000 and stamped v2")
  void up_multipliesAndVersionsLegacyPeriodicDocuments() {
    insertLegacyPeriodic("helmet-5", EventNameEnum.NO_HELMET, "5");
    insertLegacyPeriodic("jacket-7", EventNameEnum.NO_JACKET, "7");
    insertLegacyPeriodic("helmet-12", EventNameEnum.NO_HELMET, "12");

    long migrated = migration.up();

    assertThat(migrated).isEqualTo(3);
    assertThat(timePeriodOf("helmet-5")).isEqualTo("5000");
    assertThat(timePeriodOf("jacket-7")).isEqualTo("7000");
    assertThat(timePeriodOf("helmet-12")).isEqualTo("12000");
    assertThat(schemaVersionOf("helmet-5")).isEqualTo(Event.SCHEMA_VERSION_MILLIS);
    assertThat(schemaVersionOf("jacket-7")).isEqualTo(Event.SCHEMA_VERSION_MILLIS);
    assertThat(schemaVersionOf("helmet-12")).isEqualTo(Event.SCHEMA_VERSION_MILLIS);
  }

  /**
   * The stored value must stay a BSON String. If the pipeline ever emitted a Decimal128 instead,
   * the collection would hold two BSON types for one field and the current mapper would read the
   * new ones incorrectly - the {@code BigDecimalRepresentation} opt-in that makes Decimal128 safe
   * only arrives in Spring Data MongoDB 4.2.
   */
  @Test
  @DisplayName("up(): the migrated value is still a BSON String, and the mapper still reads it")
  void up_preservesTheBsonStringRepresentation() {
    insertLegacyPeriodic("helmet-5", EventNameEnum.NO_HELMET, "5");

    migration.up();

    Object raw = rawDocument("helmet-5").get("timePeriod");
    assertThat(raw).isInstanceOf(String.class);
    assertThat(raw).isNotInstanceOf(org.bson.types.Decimal128.class);

    Event reloaded = eventRepository.findAll().get(0);
    assertThat(reloaded.getTimePeriod()).isEqualByComparingTo(new BigDecimal("5000"));
    assertThat(reloaded.getSchemaVersion()).isEqualTo(Event.SCHEMA_VERSION_MILLIS);
  }

  @Test
  @DisplayName("up(): a FALL carrying no timePeriod is left BYTE-IDENTICAL")
  void up_leavesCountableEventsByteIdentical() {
    insertLegacyFallWithoutTimePeriod("fall-1");
    insertLegacyPeriodic("helmet-5", EventNameEnum.NO_HELMET, "5");

    String before = rawJson("fall-1");

    migration.up();

    assertThat(rawJson("fall-1"))
        .as("FALL never carries a duration, so the migration must not touch it at all")
        .isEqualTo(before);
    assertThat(rawDocument("fall-1")).doesNotContainKey("schemaVersion");
  }

  @Test
  @DisplayName("up(): an already-migrated document is left BYTE-IDENTICAL")
  void up_leavesAlreadyMigratedDocumentsUntouched() {
    insertMigratedPeriodic("helmet-already", EventNameEnum.NO_HELMET, "9000");
    insertLegacyPeriodic("helmet-5", EventNameEnum.NO_HELMET, "5");

    String before = rawJson("helmet-already");

    long migrated = migration.up();

    assertThat(migrated).as("only the one legacy document is in scope").isEqualTo(1);
    assertThat(rawJson("helmet-already"))
        .as("a document already at v2 must not be multiplied a second time")
        .isEqualTo(before);
  }

  /**
   * The property that matters most operationally. A migration is run by a human under pressure,
   * often twice because the first run's log scrolled away. Selecting on the ABSENCE of
   * {@code schemaVersion} means the second run's filter matches nothing at all - idempotency by
   * construction, not by a comparison that could be off by one.
   */
  @Test
  @DisplayName("up() twice changes nothing the second time: every document is byte-identical")
  void up_isIdempotent() {
    insertLegacyPeriodic("helmet-5", EventNameEnum.NO_HELMET, "5");
    insertLegacyPeriodic("jacket-7", EventNameEnum.NO_JACKET, "7");
    insertLegacyFallWithoutTimePeriod("fall-1");
    insertMigratedPeriodic("helmet-already", EventNameEnum.NO_HELMET, "9000");

    assertThat(migration.up()).isEqualTo(2);
    Map<String, String> afterFirstRun = snapshot();

    assertThat(migration.up())
        .as("the second run must select nothing")
        .isZero();

    assertThat(snapshot())
        .as("running the migration twice must be indistinguishable from running it once")
        .isEqualTo(afterFirstRun);
  }

  /**
   * The rollback. An in-place multiplication is destructive: without a tested inverse the only
   * recovery from a bad run is a restore from backup, which for this collection means losing
   * every event recorded since the snapshot. Twenty lines of pipeline buy back the ability to
   * simply undo.
   */
  @Test
  @DisplayName("down() after up() restores every document to BYTE-IDENTICAL, schemaVersion removed")
  void upThenDown_isTheIdentity() {
    insertLegacyPeriodic("helmet-5", EventNameEnum.NO_HELMET, "5");
    insertLegacyPeriodic("jacket-7", EventNameEnum.NO_JACKET, "7");
    insertLegacyPeriodic("helmet-3600", EventNameEnum.NO_HELMET, "3600");
    insertLegacyFallWithoutTimePeriod("fall-1");

    Map<String, String> original = snapshot();

    assertThat(migration.up()).isEqualTo(3);
    assertThat(snapshot()).as("up() must actually change something").isNotEqualTo(original);

    assertThat(migration.down()).isEqualTo(3);

    assertThat(snapshot())
        .as("up then down must be the identity, field order and BSON types included")
        .isEqualTo(original);
  }

  @Test
  @DisplayName("down() is idempotent too: a second run selects nothing")
  void down_isIdempotent() {
    insertLegacyPeriodic("helmet-5", EventNameEnum.NO_HELMET, "5");

    migration.up();
    assertThat(migration.down()).isEqualTo(1);
    Map<String, String> afterDown = snapshot();

    assertThat(migration.down()).isZero();
    assertThat(snapshot()).isEqualTo(afterDown);
  }

  /**
   * Records WHY the byte-identity above holds, so a future reader does not over-generalise it.
   *
   * <p>Decimal128 keeps a scale. {@code 5 x 1000} has scale 0 and stringifies as {@code "5000"};
   * {@code 5.9 x 1000} has scale 1 and stringifies as {@code "5900.0"}, which is numerically right
   * but not the string {@code "5900"}. The reverse division restores the original either way,
   * which is what {@link #upThenDown_isTheIdentity()} depends on.
   *
   * <p>It does not matter for the real data - the legacy producer sent {@code int(seconds)}, so
   * every stored value is integral - but it is the difference between "this migration round-trips"
   * and "this migration round-trips for the data we actually have".
   */
  @Test
  @DisplayName("scale: an integral value gains no trailing zeros, a fractional one does - both reverse exactly")
  void up_scaleBehaviourIsRecordedRatherThanAssumed() {
    insertLegacyPeriodic("integral", EventNameEnum.NO_HELMET, "5");
    insertLegacyPeriodic("fractional", EventNameEnum.NO_HELMET, "5.9");

    Map<String, String> original = snapshot();
    migration.up();

    assertThat(timePeriodOf("integral")).isEqualTo("5000");
    assertThat(timePeriodOf("fractional"))
        .as("Decimal128 preserves scale, so this is 5900.0 rather than 5900")
        .isEqualTo("5900.0");
    // Numerically correct either way - the mapper parses both into the same BigDecimal value.
    assertThat(new BigDecimal(timePeriodOf("fractional")))
        .isEqualByComparingTo(new BigDecimal("5900"));

    migration.down();
    assertThat(snapshot())
        .as("the inverse restores both, trailing zeros and all")
        .isEqualTo(original);
  }

  /**
   * A NO_HELMET whose {@code timePeriod} is absent cannot be produced by the current detector -
   * {@code events.py} raises on construction if a periodic event has no {@code time_period_ms} -
   * but the collection predates that validation. Multiplying a missing value would write a null
   * where there was previously nothing; the filter excludes it instead.
   */
  @Test
  @DisplayName("up(): a periodic document with no timePeriod is skipped, not turned into null")
  void up_skipsPeriodicDocumentsWithoutATimePeriod() {
    Document withoutDuration = legacyDocument("helmet-null", EventNameEnum.NO_HELMET.name());
    withoutDuration.remove("timePeriod");
    mongoTemplate.getCollection(COLLECTION).insertOne(withoutDuration);

    String before = rawJson("helmet-null");

    assertThat(migration.up()).isZero();
    assertThat(rawJson("helmet-null")).isEqualTo(before);
  }

  // --- fixture helpers -------------------------------------------------------------------------

  /**
   * The exact shape {@code EventRepositoryIT} observed Spring Data MongoDB 4.0.3 write: both
   * BigDecimals as BSON Strings, {@code startTime} as a BSON 64-bit int, {@code _class} last, and
   * no {@code schemaVersion} key at all.
   */
  private static Document legacyDocument(String cameraName, String eventType) {
    Document document = new Document();
    document.put("cameraName", cameraName);
    document.put("confidencePercentage", "90");
    document.put("eventType", eventType);
    document.put("isProcessed", "false");
    document.put("timePeriod", "0");
    document.put("startTime", START_TIME);
    document.put("endTime", START_TIME + 5_000L);
    document.put("_class", Event.class.getName());
    return document;
  }

  private void insertLegacyPeriodic(String cameraName, EventNameEnum type, String seconds) {
    Document document = legacyDocument(cameraName, type.name());
    document.put("timePeriod", seconds);
    mongoTemplate.getCollection(COLLECTION).insertOne(document);
  }

  private void insertLegacyFallWithoutTimePeriod(String cameraName) {
    Document document = legacyDocument(cameraName, EventNameEnum.FALL.name());
    document.remove("timePeriod");
    mongoTemplate.getCollection(COLLECTION).insertOne(document);
  }

  private void insertMigratedPeriodic(String cameraName, EventNameEnum type, String millis) {
    Document document = legacyDocument(cameraName, type.name());
    document.put("timePeriod", millis);
    document.put("schemaVersion", Event.SCHEMA_VERSION_MILLIS);
    mongoTemplate.getCollection(COLLECTION).insertOne(document);
  }

  // --- assertion helpers -----------------------------------------------------------------------

  private Document rawDocument(String cameraName) {
    return mongoTemplate.getCollection(COLLECTION)
        .find(new Document("cameraName", cameraName))
        .first();
  }

  /**
   * The document's extended-JSON serialisation, which is what makes the identity assertions in
   * this class genuinely byte-level.
   *
   * <p>{@link Document} extends {@code LinkedHashMap} and inherits {@code Map.equals}, which
   * ignores field ORDER and would therefore pass even if the migration moved {@code timePeriod} to
   * the end of every document. {@code toJson()} preserves order and renders the BSON type of every
   * value, so a String that became a Decimal128, or a {@code "5900"} that became {@code "5900.0"},
   * fails here rather than being quietly accepted.
   */
  private String rawJson(String cameraName) {
    return rawDocument(cameraName).toJson();
  }

  private String timePeriodOf(String cameraName) {
    return rawDocument(cameraName).getString("timePeriod");
  }

  private Integer schemaVersionOf(String cameraName) {
    return rawDocument(cameraName).getInteger("schemaVersion");
  }

  /** Every document's exact serialisation, keyed by camera name. */
  private Map<String, String> snapshot() {
    List<Document> all = new ArrayList<>();
    mongoTemplate.getCollection(COLLECTION).find().into(all);
    Map<String, String> byCamera = new LinkedHashMap<>();
    for (Document document : all) {
      byCamera.put(document.getString("cameraName"), document.toJson());
    }
    return byCamera;
  }
}
