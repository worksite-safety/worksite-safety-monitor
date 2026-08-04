package com.graduation.project.engine.event.migration;

import com.graduation.project.engine.event.model.Event;
import com.graduation.project.engine.event.model.EventNameEnum;
import com.mongodb.client.result.UpdateResult;
import java.math.BigDecimal;
import java.util.List;
import lombok.RequiredArgsConstructor;
import org.bson.Document;
import org.bson.conversions.Bson;
import org.bson.types.Decimal128;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.boot.ApplicationArguments;
import org.springframework.boot.ApplicationRunner;
import org.springframework.boot.autoconfigure.condition.ConditionalOnProperty;
import org.springframework.data.mongodb.core.MongoTemplate;
import org.springframework.stereotype.Component;

/**
 * One-shot, reversible migration of pre-existing periodic events from seconds to milliseconds.
 *
 * <h2>Scope</h2>
 *
 * <p>Only {@code NO_HELMET} and {@code NO_JACKET} documents that do not yet carry a
 * {@code schemaVersion}. The narrowness is not an optimisation, it is the correctness argument:
 * those are the only two event types that ever carry a {@code timePeriod} at all. Verified
 * against the producer rather than assumed - {@code detector/src/worksite_detector/events.py}
 * raises {@code ValueError} in {@code DetectionEvent.__post_init__} both when a periodic event
 * omits {@code time_period_ms} and when a countable event supplies one, so no FALL, ARMS_UP or
 * FRONT_BEND document can hold a duration to be converted.
 *
 * <h2>Why an aggregation pipeline and not $mul</h2>
 *
 * <p>{@code Event.timePeriod} is a {@link BigDecimal} and Spring Data MongoDB 4.0.3 persists
 * BigDecimal as a BSON <em>String</em>, not Decimal128 - pinned by
 * {@code EventRepositoryIT#timePeriodIsStoredAsBsonString}. {@code $mul} cannot multiply a string,
 * so the value has to be parsed, scaled and re-serialised server-side:
 * {@code $toDecimal -> $multiply -> $toString}.
 *
 * <p>{@code $toDecimal} rather than {@code $toDouble}. Binary floating point cannot represent most
 * decimal fractions, so {@code $toDouble} would turn exact strings into values whose
 * {@code $toString} carries artifacts, permanently, in a field that is currently exact.
 * Decimal128 is exact for these magnitudes and its {@code $toString} is the plain digits.
 *
 * <p>The output stays a BSON String. Writing Decimal128 today would be read incorrectly by the
 * current mapper: the {@code MongoCustomConversions.BigDecimalRepresentation} opt-in that makes
 * Decimal128 the safe choice only arrives in Spring Data MongoDB 4.2, inside the Boot 3.5.x
 * upgrade range. Migrating the unit and the BSON type in one step would couple this change to
 * that upgrade for no benefit.
 *
 * <h2>Safety</h2>
 *
 * <ul>
 *   <li><b>Off by default.</b> {@code @ConditionalOnProperty} with no {@code matchIfMissing}, so
 *       the bean does not exist unless {@code event.migration.periodic-to-millis.enabled=true}. A
 *       destructive in-place update must never be one pod restart away from running.</li>
 *   <li><b>Idempotent by construction.</b> {@link #up()} selects on the ABSENCE of
 *       {@code schemaVersion} and sets it, so the second run's filter matches nothing. This is a
 *       property of the query, not of a comparison that could be off by one.</li>
 *   <li><b>Reversible.</b> {@link #down()} is the exact inverse, including removing
 *       {@code schemaVersion} again so a rolled-back document is byte-identical to the original.
 *       It is the only credible rollback for an in-place update; a restore from backup would
 *       discard every event recorded since the snapshot.</li>
 * </ul>
 */
@Component
@ConditionalOnProperty(name = "event.migration.periodic-to-millis.enabled", havingValue = "true")
@RequiredArgsConstructor
public class PeriodicTimePeriodMigration implements ApplicationRunner {

  static final String COLLECTION = "event";

  static final List<String> PERIODIC_TYPES =
      List.of(EventNameEnum.NO_HELMET.name(), EventNameEnum.NO_JACKET.name());

  /**
   * Explicitly Decimal128 rather than the int literal {@code 1000}. MongoDB would promote an int
   * operand to decimal anyway, but stating it removes the question from the reader and from any
   * future server whose promotion rules differ.
   */
  private static final Decimal128 THOUSAND = new Decimal128(new BigDecimal("1000"));

  private static final Logger logger = LoggerFactory.getLogger(PeriodicTimePeriodMigration.class);

  private final MongoTemplate mongoTemplate;

  @Override
  public void run(ApplicationArguments args) {
    logger.warn("event.migration.periodic-to-millis.enabled=true - migrating periodic timePeriod "
        + "from seconds to milliseconds. Disable this property again after the run.");
    long migrated = up();
    logger.warn("Migration complete: {} periodic event(s) converted to milliseconds.", migrated);
  }

  /**
   * Seconds -> milliseconds. Multiplies {@code timePeriod} by 1000 and stamps
   * {@link Event#SCHEMA_VERSION_MILLIS}.
   *
   * @return how many documents were modified; 0 on every run after the first
   */
  public long up() {
    Bson filter = new Document("eventType", new Document("$in", PERIODIC_TYPES))
        .append("schemaVersion", new Document("$exists", false))
        // A periodic document with no duration cannot come from the current detector, but the
        // collection predates that validation. Excluded rather than converted, because
        // $multiply on a missing field yields null - writing a null where there was nothing.
        .append("timePeriod", new Document("$ne", null));

    List<Bson> pipeline = List.of(
        new Document("$set", new Document()
            .append("timePeriod", new Document("$toString",
                new Document("$multiply",
                    List.of(new Document("$toDecimal", "$timePeriod"), THOUSAND))))
            .append("schemaVersion", Event.SCHEMA_VERSION_MILLIS)));

    UpdateResult result = mongoTemplate.getCollection(COLLECTION).updateMany(filter, pipeline);
    logger.info("up(): matched={} modified={}", result.getMatchedCount(),
        result.getModifiedCount());
    return result.getModifiedCount();
  }

  /**
   * Milliseconds -> seconds, and the {@code schemaVersion} stamp removed so the document returns
   * to exactly its pre-migration bytes.
   *
   * @return how many documents were modified; 0 on every run after the first
   */
  public long down() {
    Bson filter = new Document("eventType", new Document("$in", PERIODIC_TYPES))
        .append("schemaVersion", Event.SCHEMA_VERSION_MILLIS)
        .append("timePeriod", new Document("$ne", null));

    List<Bson> pipeline = List.of(
        new Document("$set", new Document("timePeriod", new Document("$toString",
            new Document("$divide",
                List.of(new Document("$toDecimal", "$timePeriod"), THOUSAND))))),
        // Removed, not set to 1: absence is what "seconds" means, so restoring the field to any
        // value would leave the document distinguishable from the one that was migrated.
        new Document("$unset", "schemaVersion"));

    UpdateResult result = mongoTemplate.getCollection(COLLECTION).updateMany(filter, pipeline);
    logger.info("down(): matched={} modified={}", result.getMatchedCount(),
        result.getModifiedCount());
    return result.getModifiedCount();
  }
}
