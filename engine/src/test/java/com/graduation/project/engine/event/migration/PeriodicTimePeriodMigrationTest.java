package com.graduation.project.engine.event.migration;

import static org.assertj.core.api.Assertions.assertThat;
import static org.mockito.ArgumentMatchers.any;
import static org.mockito.ArgumentMatchers.anyList;
import static org.mockito.Mockito.mock;
import static org.mockito.Mockito.times;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.when;

import com.mongodb.client.MongoCollection;
import com.mongodb.client.result.UpdateResult;
import org.bson.Document;
import org.bson.conversions.Bson;
import org.junit.jupiter.api.DisplayName;
import org.junit.jupiter.api.Test;
import org.springframework.boot.autoconfigure.AutoConfigurations;
import org.springframework.boot.test.context.runner.ApplicationContextRunner;
import org.springframework.data.mongodb.core.MongoTemplate;

/**
 * The GUARD on {@link PeriodicTimePeriodMigration}, tested in both directions.
 *
 * <p>{@code PeriodicTimePeriodMigrationIT} asserts the negative case against the real application
 * context - the bean is absent by default. The positive case cannot be tested the same way: any
 * {@code @SpringBootTest} that overrides a property gets its own context cache key, and a second
 * context in this suite starts a second {@code @KafkaListener} container in the same consumer
 * group as the first, which then loses the topic's only partition. That failure is measured and
 * documented in {@code src/test/resources/application.yml}.
 *
 * <p>{@link ApplicationContextRunner} sidesteps it entirely: it builds a bare context containing
 * only what is registered here, so there is no listener, no broker and no Docker, and the
 * condition is still evaluated by the real Spring machinery rather than being assumed.
 */
class PeriodicTimePeriodMigrationTest {

  private static final String ENABLED = "event.migration.periodic-to-millis.enabled";

  private final ApplicationContextRunner contextRunner = new ApplicationContextRunner()
      .withBean(MongoTemplate.class, () -> mock(MongoTemplate.class))
      .withConfiguration(AutoConfigurations.of())
      .withUserConfiguration(PeriodicTimePeriodMigration.class);

  @Test
  @DisplayName("property absent: the migration bean is NOT created")
  void propertyAbsent_beanIsNotCreated() {
    contextRunner.run(context ->
        assertThat(context).doesNotHaveBean(PeriodicTimePeriodMigration.class));
  }

  @Test
  @DisplayName("property=false: the migration bean is NOT created")
  void propertyFalse_beanIsNotCreated() {
    contextRunner.withPropertyValues(ENABLED + "=false").run(context ->
        assertThat(context).doesNotHaveBean(PeriodicTimePeriodMigration.class));
  }

  /**
   * Without this, "the migration is off by default" would be indistinguishable from "the migration
   * can never run at all" - a guard that is stuck shut looks exactly like a guard that works,
   * right up to the moment an operator needs it.
   */
  @Test
  @DisplayName("property=true: the migration bean IS created")
  void propertyTrue_beanIsCreated() {
    contextRunner.withPropertyValues(ENABLED + "=true").run(context ->
        assertThat(context).hasSingleBean(PeriodicTimePeriodMigration.class));
  }

  @Test
  @DisplayName("run() performs the UP migration, not the reverse")
  @SuppressWarnings("unchecked")
  void run_delegatesToUp() {
    MongoTemplate mongoTemplate = mock(MongoTemplate.class);
    MongoCollection<Document> collection = mock(MongoCollection.class);
    UpdateResult result = mock(UpdateResult.class);

    when(mongoTemplate.getCollection(PeriodicTimePeriodMigration.COLLECTION))
        .thenReturn(collection);
    when(collection.updateMany(any(Bson.class), anyList())).thenReturn(result);
    when(result.getModifiedCount()).thenReturn(7L);

    new PeriodicTimePeriodMigration(mongoTemplate).run(null);

    // The filter distinguishes the two directions: up() selects documents with NO schemaVersion,
    // down() selects documents that HAVE it.
    org.mockito.ArgumentCaptor<Bson> filterCaptor =
        org.mockito.ArgumentCaptor.forClass(Bson.class);
    verify(collection, times(1)).updateMany(filterCaptor.capture(), anyList());

    Document filter = (Document) filterCaptor.getValue();
    assertThat(filter.get("schemaVersion"))
        .as("run() must select unversioned documents, i.e. it must call up()")
        .isEqualTo(new Document("$exists", false));
  }
}
