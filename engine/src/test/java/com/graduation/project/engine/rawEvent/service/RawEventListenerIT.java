package com.graduation.project.engine.rawEvent.service;

import static org.assertj.core.api.Assertions.assertThat;
import static org.awaitility.Awaitility.await;

import ch.qos.logback.classic.Level;
import ch.qos.logback.classic.spi.ILoggingEvent;
import ch.qos.logback.core.read.ListAppender;
import com.fasterxml.jackson.databind.ObjectMapper;
import com.graduation.project.engine.AbstractIntegrationTest;
import com.graduation.project.engine.event.model.Event;
import com.graduation.project.engine.event.model.EventNameEnum;
import com.graduation.project.engine.rawEvent.model.RawEvent;
import java.math.BigDecimal;
import java.time.Duration;
import java.util.ArrayList;
import java.util.Collection;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.UUID;
import java.util.concurrent.TimeUnit;
import org.apache.kafka.clients.consumer.Consumer;
import org.apache.kafka.clients.consumer.ConsumerRecord;
import org.apache.kafka.clients.consumer.ConsumerRecords;
import org.apache.kafka.clients.producer.KafkaProducer;
import org.apache.kafka.clients.producer.ProducerConfig;
import org.apache.kafka.clients.producer.ProducerRecord;
import org.apache.kafka.common.serialization.StringSerializer;
import org.bson.Document;
import org.junit.jupiter.api.AfterAll;
import org.junit.jupiter.api.AfterEach;
import org.junit.jupiter.api.BeforeAll;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.DisplayName;
import org.junit.jupiter.api.MethodOrderer;
import org.junit.jupiter.api.Order;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.TestMethodOrder;
import org.slf4j.LoggerFactory;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.data.mongodb.core.MongoTemplate;
import org.springframework.data.mongodb.core.query.Criteria;
import org.springframework.data.mongodb.core.query.Query;
import org.springframework.kafka.config.KafkaListenerEndpointRegistry;
import org.springframework.kafka.config.TopicBuilder;
import org.springframework.kafka.core.ConsumerFactory;
import org.springframework.kafka.core.KafkaAdmin;
import org.springframework.kafka.listener.MessageListenerContainer;
import org.springframework.kafka.test.utils.ContainerTestUtils;

/**
 * End-to-end tests for the only consumer in the system: {@code RawEventService.listener}, reached
 * through a real broker, the real {@code ConsumerFactory}/{@code ConcurrentKafkaListenerContainerFactory}
 * and a real MongoDB.
 *
 * <h2>Why these are integration tests and not unit tests</h2>
 *
 * <p>{@link RawEventServiceTest} already covers the listener's routing rules with mocks. It
 * cannot cover any of the defects exercised here, because all of them live between the broker
 * and the listener method:
 *
 * <ul>
 *   <li>a value that cannot be deserialised fails inside {@code Consumer.poll()}, i.e. before
 *       any {@code CommonErrorHandler} is given a record and before the listener method is
 *       entered at all;</li>
 *   <li>{@code auto.offset.reset} decides which records ever reach the listener;</li>
 *   <li>whether an exception thrown by the listener blocks the partition is a property of the
 *       container's error handler, which a mock-based test never instantiates.</li>
 * </ul>
 *
 * <h2>Ordering is load-bearing</h2>
 *
 * <p>{@link #poisonPillDoesNotBlockTheRestOfThePartition()} is deliberately {@code @Order(4)},
 * last. Before the fix it wedges the consumer group on the topic's only partition permanently -
 * that is the point of the test - and a wedged group cannot be un-wedged by restarting the
 * container, because the offset it is stuck on is exactly the offset it would resume from. Any
 * test scheduled after it would therefore fail for a reason that has nothing to do with what it
 * asserts. The order makes each of the four verdicts independently attributable.
 *
 * <p>For the same reason {@link #beforeEach()}/{@link #afterEach()} start and stop the listener
 * container around every test: a container left spinning on a poison pill burns a CPU core and
 * floods the log for the remainder of the Failsafe JVM, which is shared with every other IT
 * class.
 *
 * <p>The offset-reset test uses its own topic and its own consumer, so it is unaffected by both.
 */
@TestMethodOrder(MethodOrderer.OrderAnnotation.class)
class RawEventListenerIT extends AbstractIntegrationTest {

  private static final String COLLECTION = "event";

  /** Long enough to absorb a consumer-group rebalance, short enough to fail a build promptly. */
  private static final Duration TIMEOUT = Duration.ofSeconds(20);

  private static final ObjectMapper MAPPER = new ObjectMapper();

  private static KafkaProducer<String, String> producer;

  @Autowired
  private MongoTemplate mongoTemplate;

  @Autowired
  private KafkaAdmin kafkaAdmin;

  @Autowired
  private ConsumerFactory<String, RawEvent> consumerFactory;

  @Autowired
  private KafkaListenerEndpointRegistry endpointRegistry;

  /**
   * The topic the listener is expected to consume. Reading it from the same property
   * {@code KafkaTopicConfig} uses is the whole reason the listener's topic has to be
   * externalised: a hardcoded {@code topics = "rawEvents"} cannot be pointed at the topic these
   * tests create.
   */
  @Value("${kafka.raw-event.topic}")
  private String topic;

  @Value("${event.periodic.min-duration-ms}")
  private long minPeriodicDurationMs;

  private ListAppender<ILoggingEvent> serviceLogs;

  private ListAppender<ILoggingEvent> containerLogs;

  @BeforeAll
  static void startProducer() {
    Map<String, Object> props = new LinkedHashMap<>();
    props.put(ProducerConfig.BOOTSTRAP_SERVERS_CONFIG, KAFKA.getBootstrapServers());
    props.put(ProducerConfig.KEY_SERIALIZER_CLASS_CONFIG, StringSerializer.class);
    // A String producer, not a JsonSerializer: two of the four tests have to put bytes on the
    // topic that no serialiser would ever produce, which is precisely the scenario an
    // unauthenticated topic fed by a separate Python process exposes.
    props.put(ProducerConfig.VALUE_SERIALIZER_CLASS_CONFIG, StringSerializer.class);
    producer = new KafkaProducer<>(props);
  }

  @AfterAll
  static void stopProducer() {
    if (producer != null) {
      producer.close(Duration.ofSeconds(5));
    }
  }

  @BeforeEach
  void beforeEach() {
    mongoTemplate.getCollection(COLLECTION).deleteMany(new Document());

    serviceLogs = attach(RawEventService.class.getName());
    containerLogs = attach("org.springframework.kafka.listener");

    for (MessageListenerContainer container : endpointRegistry.getListenerContainers()) {
      if (!container.isRunning()) {
        container.start();
      }
      ContainerTestUtils.waitForAssignment(container, 1);
    }
  }

  @AfterEach
  void afterEach() {
    for (MessageListenerContainer container : endpointRegistry.getListenerContainers()) {
      container.stop();
    }
    detach(RawEventService.class.getName(), serviceLogs);
    detach("org.springframework.kafka.listener", containerLogs);
  }

  @Test
  @Order(1)
  @DisplayName("a well-formed NO_HELMET above the threshold is consumed and stored exactly once")
  void wellFormedEventIsPersisted() {
    String camera = "camera-happy-" + UUID.randomUUID();
    long startTime = 1_700_000_000_000L;
    long timePeriod = minPeriodicDurationMs + 5_000L;

    send(topic, payload(camera, EventNameEnum.NO_HELMET.name(), 0.93, timePeriod, startTime));

    await().atMost(TIMEOUT).pollInterval(200, TimeUnit.MILLISECONDS).untilAsserted(() -> {
      List<Event> stored = findByCamera(camera);
      assertThat(stored).hasSize(1);

      Event event = stored.get(0);
      assertThat(event.getEventType()).isEqualTo(EventNameEnum.NO_HELMET.name());
      assertThat(event.getCameraName()).isEqualTo(camera);
      assertThat(event.getStartTime()).isEqualTo(startTime);
      assertThat(event.getIsProcessed()).isEqualTo("false");
      assertThat(event.getTimePeriod()).isEqualByComparingTo(BigDecimal.valueOf(timePeriod));
      assertThat(event.getConfidencePercentage()).isEqualByComparingTo(new BigDecimal("0.93"));
    });
  }

  /**
   * A brand-new consumer group must see what is already on the topic.
   *
   * <p>Left unset, {@code ConsumerConfig.AUTO_OFFSET_RESET_CONFIG} falls back to the Kafka client
   * default of {@code latest}. Every consequence of that is silent: the first deployment against
   * an existing topic, any group-id rename, and any {@code kafka-consumer-groups --delete} all
   * discard the backlog without a single log line. {@code KafkaConsumerConfig} therefore supplies
   * {@code earliest} with {@code putIfAbsent}, as a default rather than a second hardcoding.
   *
   * <p>What this asserts is that DEFAULT, which is why {@code src/test/resources/application.yml}
   * deliberately does not set {@code spring.kafka.consumer.auto-offset-reset}. That key is live
   * now - it was inert, along with every other {@code spring.kafka.consumer.*} key - and stating
   * it in the test configuration would let this test go on passing on the strength of that file
   * long after the shipped default had regressed.
   *
   * <p>Uses its own topic so that neither the poison pill nor the malformed payload from the
   * other tests can change what "already on the topic" means here.
   */
  @Test
  @Order(2)
  @DisplayName("a fresh consumer group reads records that predate it (auto.offset.reset=earliest)")
  void freshConsumerGroupSeesExistingRecords() {
    String freshTopic = "rawEvents-offset-reset-" + UUID.randomUUID();
    kafkaAdmin.createOrModifyTopics(TopicBuilder.name(freshTopic).partitions(1).replicas(1).build());

    String camera = "camera-backlog-" + UUID.randomUUID();
    send(freshTopic, payload(camera, EventNameEnum.FALL.name(), 0.88, null, 1_700_000_000_000L));

    List<String> seen = new ArrayList<>();
    // Created only AFTER the record is on the broker, and with a group id that has never
    // committed an offset - the exact situation auto.offset.reset governs.
    try (Consumer<String, RawEvent> consumer =
        consumerFactory.createConsumer("it-fresh-group-" + UUID.randomUUID(), "")) {
      consumer.subscribe(List.of(freshTopic));

      long deadline = System.currentTimeMillis() + TIMEOUT.toMillis();
      while (System.currentTimeMillis() < deadline && !seen.contains(camera)) {
        ConsumerRecords<String, RawEvent> records = consumer.poll(Duration.ofMillis(500));
        for (ConsumerRecord<String, RawEvent> record : records) {
          if (record.value() != null) {
            seen.add(record.value().getCameraName());
          }
        }
      }
    }

    assertThat(seen)
        .as("a consumer group created after the record was produced must still receive it")
        .contains(camera);
  }

  /**
   * A payload that deserialises cleanly but carries no {@code eventType}.
   *
   * <p>{@code RawEvent} is {@code @JsonIgnoreProperties(ignoreUnknown = true)} and has no
   * required fields, so the omission produces a {@code RawEvent} with a null {@code eventType}
   * and the listener's first {@code .equals(...)} throws. The contract asserted here is that the
   * listener drops it itself - one WARNING, nothing persisted, nothing thrown back into the
   * container - rather than delegating the problem to the container's retry machinery.
   */
  @Test
  @Order(3)
  @DisplayName("a payload with no eventType is dropped with one WARNING and does not stall the topic")
  void missingEventTypeIsDroppedAndTheNextEventStillArrives() {
    String malformedCamera = "camera-no-event-type-" + UUID.randomUUID();
    String validCamera = "camera-after-null-type-" + UUID.randomUUID();

    Map<String, Object> withoutEventType = new LinkedHashMap<>();
    withoutEventType.put("cameraName", malformedCamera);
    withoutEventType.put("confidencePercentage", 0.91);
    withoutEventType.put("isProcessed", "false");
    withoutEventType.put("timePeriod", 5_000L);
    withoutEventType.put("startTime", 1_700_000_000_000L);

    send(topic, json(withoutEventType));
    send(topic, payload(validCamera, EventNameEnum.FALL.name(), 0.9, null, 1_700_000_000_000L));

    await().atMost(TIMEOUT).pollInterval(200, TimeUnit.MILLISECONDS)
        .untilAsserted(() -> assertThat(findByCamera(validCamera)).hasSize(1));

    assertThat(findByCamera(malformedCamera))
        .as("an event with no type must not be stored")
        .isEmpty();

    assertThat(warnings(serviceLogs))
        .as("exactly one WARNING describing the drop")
        .hasSize(1);

    assertThat(errors(containerLogs))
        .as("the container's error handler must never see this - the listener owns the drop")
        .isEmpty();
  }

  /**
   * The poison pill: bytes on the topic that no {@code JsonDeserializer} can turn into a
   * {@code RawEvent}.
   *
   * <p>Without an {@code ErrorHandlingDeserializer} the failure happens inside
   * {@code Consumer.poll()}, so no {@code ConsumerRecord} ever exists and no error handler can
   * be given one to skip. The consumer's position never advances past the offset, the next poll
   * re-reads the same bytes and throws again, and every later record on that partition is
   * unreachable for as long as the application runs.
   */
  @Test
  @Order(4)
  @DisplayName("an unparseable message does not block every later message on the partition")
  void poisonPillDoesNotBlockTheRestOfThePartition() {
    String camera = "camera-after-poison-" + UUID.randomUUID();

    send(topic, "{not json");
    send(topic, payload(camera, EventNameEnum.FALL.name(), 0.87, null, 1_700_000_000_000L));

    await()
        .alias("the valid message produced after an unparseable one must still be consumed")
        .atMost(TIMEOUT).pollInterval(200, TimeUnit.MILLISECONDS)
        .untilAsserted(() -> assertThat(findByCamera(camera)).hasSize(1));
  }

  // --- helpers -------------------------------------------------------------------------------

  /**
   * The exact wire shape {@code detector/src/worksite_detector/events.py} emits: all six keys
   * always present, {@code isProcessed} as the string {@code "false"}, both time fields in
   * milliseconds, and {@code timePeriod} explicitly null for countable events rather than
   * omitted.
   */
  private static String payload(String cameraName, String eventType, double confidence,
      Long timePeriodMs, long startTimeMs) {
    Map<String, Object> body = new LinkedHashMap<>();
    body.put("cameraName", cameraName);
    body.put("confidencePercentage", confidence);
    body.put("eventType", eventType);
    body.put("isProcessed", "false");
    body.put("timePeriod", timePeriodMs);
    body.put("startTime", startTimeMs);
    return json(body);
  }

  private static String json(Map<String, Object> body) {
    try {
      return MAPPER.writeValueAsString(body);
    } catch (Exception e) {
      throw new IllegalStateException(e);
    }
  }

  /** Synchronous on purpose: a test must not race its own producer. */
  private static void send(String topic, String value) {
    try {
      producer.send(new ProducerRecord<>(topic, value)).get(10, TimeUnit.SECONDS);
    } catch (Exception e) {
      throw new IllegalStateException("could not publish to " + topic, e);
    }
  }

  private List<Event> findByCamera(String cameraName) {
    return mongoTemplate.find(
        Query.query(Criteria.where("cameraName").is(cameraName)), Event.class, COLLECTION);
  }

  private static ListAppender<ILoggingEvent> attach(String loggerName) {
    ListAppender<ILoggingEvent> appender = new ListAppender<>();
    appender.start();
    ((ch.qos.logback.classic.Logger) LoggerFactory.getLogger(loggerName)).addAppender(appender);
    return appender;
  }

  private static void detach(String loggerName, ListAppender<ILoggingEvent> appender) {
    if (appender != null) {
      ((ch.qos.logback.classic.Logger) LoggerFactory.getLogger(loggerName)).detachAppender(appender);
      appender.stop();
    }
  }

  private static List<ILoggingEvent> warnings(ListAppender<ILoggingEvent> appender) {
    return atLevel(appender.list, Level.WARN);
  }

  private static List<ILoggingEvent> errors(ListAppender<ILoggingEvent> appender) {
    return atLevel(appender.list, Level.ERROR);
  }

  private static List<ILoggingEvent> atLevel(Collection<ILoggingEvent> events, Level level) {
    // Copied first: the appender's list is written from a Kafka consumer thread.
    return new ArrayList<>(events).stream().filter(e -> e.getLevel() == level).toList();
  }
}
