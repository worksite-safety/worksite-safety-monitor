package com.graduation.project.engine.core.messageBrokerConfig;

import static java.nio.charset.StandardCharsets.UTF_8;
import static org.assertj.core.api.Assertions.assertThat;

import ch.qos.logback.classic.Level;
import ch.qos.logback.classic.spi.ILoggingEvent;
import ch.qos.logback.core.read.ListAppender;
import com.graduation.project.engine.rawEvent.model.RawEvent;
import java.util.List;
import java.util.Map;
import org.apache.kafka.clients.consumer.ConsumerConfig;
import org.apache.kafka.clients.consumer.ConsumerRecord;
import org.apache.kafka.common.serialization.Deserializer;
import org.apache.kafka.common.serialization.StringDeserializer;
import org.junit.jupiter.api.DisplayName;
import org.junit.jupiter.api.Test;
import org.slf4j.LoggerFactory;
import org.springframework.boot.autoconfigure.AutoConfigurations;
import org.springframework.boot.autoconfigure.kafka.KafkaAutoConfiguration;
import org.springframework.boot.test.context.assertj.AssertableApplicationContext;
import org.springframework.boot.test.context.runner.ApplicationContextRunner;
import org.springframework.kafka.config.ConcurrentKafkaListenerContainerFactory;
import org.springframework.kafka.core.ConsumerFactory;
import org.springframework.kafka.listener.CommonErrorHandler;
import org.springframework.kafka.listener.ConcurrentMessageListenerContainer;
import org.springframework.kafka.listener.ContainerProperties;
import org.springframework.kafka.listener.DefaultErrorHandler;
import org.springframework.kafka.listener.ListenerExecutionFailedException;
import org.springframework.kafka.support.serializer.ErrorHandlingDeserializer;
import org.springframework.util.backoff.FixedBackOff;

/**
 * What {@code spring.kafka.*} means for this application's consumer.
 *
 * <h2>Why an {@link ApplicationContextRunner} and not a {@code @SpringBootTest}</h2>
 *
 * <p>The defect this class exists to prevent is a wiring defect: {@link KafkaConsumerConfig}
 * declares {@code kafkaListenerContainerFactory} under the exact bean name Spring Boot's own
 * auto-configured factory uses, so Boot backs off. Whether the resulting factory has been through
 * {@code ConcurrentKafkaListenerContainerFactoryConfigurer} is therefore only observable when
 * {@link KafkaAutoConfiguration} is in the picture <em>and</em> the user configuration can win the
 * bean name - which is exactly what the runner reproduces, in-process, in milliseconds and without
 * a broker.
 *
 * <p>A {@code @SpringBootTest} cannot do this job: the single shared IT context is pinned to one
 * set of properties on purpose (see {@code AbstractIntegrationTest}), and the whole question here
 * is "what happens when the properties change". Each test below gets its own context with its own
 * properties, and none of them starts a listener - {@code RawEventService} is not in scope, so no
 * {@code @KafkaListener} is registered and nothing dials a broker.
 *
 * <h2>The three things that must survive the configurer</h2>
 *
 * <p>Applying the configurer hands Boot's {@code KafkaProperties} defaults a chance to overwrite
 * three decisions this codebase made on purpose, each with its own defect behind it: the
 * {@code ErrorHandlingDeserializer} wrapping (poison pill), {@code auto.offset.reset=earliest}
 * (silent backlog loss) and the no-retry error handler (ten emails per malformed FALL). Those are
 * pinned below, next to the properties they could have been settled by.
 */
class KafkaConsumerConfigTest {

  /** Any topic name: nothing here connects, and no assertion depends on which topic it is. */
  private static final String TOPIC = "rawEvents";

  private static final String BROKER = "spring.kafka.bootstrap-servers=broker-1:9092";

  private final ApplicationContextRunner contexts = new ApplicationContextRunner()
      .withConfiguration(AutoConfigurations.of(KafkaAutoConfiguration.class))
      .withUserConfiguration(KafkaConsumerConfig.class);

  // -------------------------------------------------------------------------------------------
  // The defect: spring.kafka.* must reach the consumer and the container
  // -------------------------------------------------------------------------------------------

  @Test
  @DisplayName("spring.kafka.consumer.* reaches the consumer factory")
  void consumerPropertiesAreApplied() {
    contexts.withPropertyValues(
            BROKER,
            // Chosen because it is observable from outside without a broker AND it is the
            // property whose absence is most expensive: max.poll.records bounds how much work
            // one poll hands the listener, so an operator tuning it and getting nothing is the
            // whole shape of this defect.
            "spring.kafka.consumer.max-poll-records=7",
            "spring.kafka.consumer.client-id=engine-consumer",
            "spring.kafka.consumer.enable-auto-commit=false")
        .run(context -> {
          Map<String, Object> props = consumerProperties(context);

          assertThat(props)
              .as("spring.kafka.consumer.max-poll-records must not be silently discarded")
              .containsEntry(ConsumerConfig.MAX_POLL_RECORDS_CONFIG, 7)
              .containsEntry(ConsumerConfig.CLIENT_ID_CONFIG, "engine-consumer")
              .containsEntry(ConsumerConfig.ENABLE_AUTO_COMMIT_CONFIG, false)
              // A List, not a String: KafkaProperties models bootstrap-servers as a list and
              // ConsumerConfig declares the key as Type.LIST. Pinned so that a future upgrade
              // changing the shape is a failing test rather than a runtime surprise.
              .containsEntry(ConsumerConfig.BOOTSTRAP_SERVERS_CONFIG, List.of("broker-1:9092"));
        });
  }

  @Test
  @DisplayName("spring.kafka.listener.* reaches the listener container")
  void listenerPropertiesAreApplied() {
    contexts.withPropertyValues(
            BROKER,
            "spring.kafka.listener.client-id=engine-listener",
            "spring.kafka.listener.poll-timeout=1234ms",
            "spring.kafka.listener.concurrency=3",
            "spring.kafka.listener.ack-mode=MANUAL")
        .run(context -> {
          ConcurrentMessageListenerContainer<?, ?> container = container(context);
          ContainerProperties properties = container.getContainerProperties();

          assertThat(properties.getClientId()).isEqualTo("engine-listener");
          assertThat(properties.getPollTimeout()).isEqualTo(1234L);
          assertThat(properties.getAckMode()).isEqualTo(ContainerProperties.AckMode.MANUAL);
          assertThat(container.getConcurrency()).isEqualTo(3);
        });
  }

  // -------------------------------------------------------------------------------------------
  // The deliberate decisions the configurer must not settle
  // -------------------------------------------------------------------------------------------

  @Test
  @DisplayName("auto.offset.reset defaults to earliest, and configuration can still override it")
  void autoOffsetResetDefaultsToEarliestAndRemainsConfigurable() {
    // Unset, the Kafka client default is "latest": a consumer group that has never committed
    // silently discards everything already on the topic. KafkaProperties has no default of its
    // own for this key, so making the property live must not mean losing the safe value.
    contexts.withPropertyValues(BROKER).run(context ->
        assertThat(consumerProperties(context))
            .as("an unset auto-offset-reset must still mean earliest, not the client's latest")
            .containsEntry(ConsumerConfig.AUTO_OFFSET_RESET_CONFIG, "earliest"));

    // ...and the safe default must be a default, not a second hardcoding. An operator who asks
    // for latest gets latest.
    contexts.withPropertyValues(BROKER, "spring.kafka.consumer.auto-offset-reset=latest")
        .run(context ->
            assertThat(consumerProperties(context))
                .as("spring.kafka.consumer.auto-offset-reset must be able to win")
                .containsEntry(ConsumerConfig.AUTO_OFFSET_RESET_CONFIG, "latest"));
  }

  @Test
  @DisplayName("the value deserializer stays the ErrorHandlingDeserializer-wrapped RawEvent reader")
  void deserialisersSurviveThePropertiesDefaults() {
    contexts.withPropertyValues(BROKER).run(context -> {
      ConsumerFactory<?, ?> factory = context.getBean(ConsumerFactory.class);

      assertThat(factory.getKeyDeserializer()).isInstanceOf(StringDeserializer.class);

      Deserializer<?> value = factory.getValueDeserializer();
      assertThat(value)
          .as("KafkaProperties defaults value-deserializer to StringDeserializer; the instance wins")
          .isInstanceOf(ErrorHandlingDeserializer.class);

      // The poison pill, at the only level it can be fixed: bytes that are not a RawEvent come
      // back as null instead of throwing inside Consumer.poll(), where no error handler could
      // ever be given a record to skip.
      assertThat(value.deserialize(TOPIC, "{not json".getBytes(UTF_8))).isNull();
      assertThat(value.deserialize(TOPIC, "{\"cameraName\":\"cam-1\"}".getBytes(UTF_8)))
          .isInstanceOf(RawEvent.class);

      // The class-valued keys are removed rather than left to be quietly ignored: KafkaConsumer
      // never calls configure() on a supplied instance, so a value here would be a setting that
      // reads as active and is not.
      assertThat(factory.getConfigurationProperties())
          .doesNotContainKey(ConsumerConfig.KEY_DESERIALIZER_CLASS_CONFIG)
          .doesNotContainKey(ConsumerConfig.VALUE_DESERIALIZER_CLASS_CONFIG);
    });
  }

  @Test
  @DisplayName("a configured deserializer is refused at startup rather than silently ignored")
  void aDeserialiserThisFactoryCannotHonourFailsFast() {
    contexts.withPropertyValues(BROKER,
            "spring.kafka.consumer.value-deserializer=org.apache.kafka.common.serialization.ByteArrayDeserializer")
        .run(context -> assertThat(context)
            .hasFailed()
            .getFailure()
            .hasMessageContaining("spring.kafka.consumer.value-deserializer"));
  }

  @Test
  @DisplayName("the no-retry error handler survives the configurer and a CommonErrorHandler bean")
  void errorHandlerIsNotOverriddenByTheConfigurer() {
    // The configurer applies any single CommonErrorHandler bean in the context to the factory.
    // This one retries ten times - spring-kafka's own default, and the behaviour that turns one
    // malformed FALL into ten rounds of email to every user in the database.
    contexts.withPropertyValues(BROKER)
        .withBean("retryingErrorHandler", CommonErrorHandler.class,
            () -> new DefaultErrorHandler(new FixedBackOff(0L, 9L)))
        .run(context -> {
          ListAppender<ILoggingEvent> logs = attach(KafkaConsumerConfig.class.getName());
          try {
            CommonErrorHandler handler = container(context).getCommonErrorHandler();

            assertThat(handler)
                .as("this factory's error handler is set AFTER configure(), so it wins")
                .isNotSameAs(context.getBean("retryingErrorHandler"));

            // handleOne returns true only when there is nothing left to retry. With
            // FixedBackOff(0, 0) that is the FIRST failure; with spring-kafka's default
            // FixedBackOff(0, 9) it would be false nine times first.
            boolean recovered = handler.handleOne(
                new ListenerExecutionFailedException("Listener failed",
                    new IllegalStateException("boom")),
                new ConsumerRecord<>(TOPIC, 0, 42L, "k", "v"),
                null, null);

            assertThat(recovered)
                .as("a malformed record is recovered on the first attempt, never retried")
                .isTrue();
            assertThat(warnings(logs))
                .singleElement()
                .satisfies(event -> assertThat(event.getFormattedMessage())
                    .contains(TOPIC, "42", "IllegalStateException", "boom"));
          } finally {
            detach(KafkaConsumerConfig.class.getName(), logs);
          }
        });
  }

  // --- helpers ---------------------------------------------------------------------------------

  private static Map<String, Object> consumerProperties(AssertableApplicationContext context) {
    return context.getBean(ConsumerFactory.class).getConfigurationProperties();
  }

  /**
   * A container built the way the {@code @KafkaListener} infrastructure builds one, so that every
   * assertion is on what the listener would actually get. Constructing it touches no network.
   */
  private static ConcurrentMessageListenerContainer<?, ?> container(
      AssertableApplicationContext context) {
    ConcurrentKafkaListenerContainerFactory<?, ?> factory =
        context.getBean(ConcurrentKafkaListenerContainerFactory.class);
    return (ConcurrentMessageListenerContainer<?, ?>) factory.createContainer(TOPIC);
  }

  private static ListAppender<ILoggingEvent> attach(String loggerName) {
    ListAppender<ILoggingEvent> appender = new ListAppender<>();
    appender.start();
    ((ch.qos.logback.classic.Logger) LoggerFactory.getLogger(loggerName)).addAppender(appender);
    return appender;
  }

  private static void detach(String loggerName, ListAppender<ILoggingEvent> appender) {
    ((ch.qos.logback.classic.Logger) LoggerFactory.getLogger(loggerName)).detachAppender(appender);
    appender.stop();
  }

  private static List<ILoggingEvent> warnings(ListAppender<ILoggingEvent> appender) {
    return appender.list.stream().filter(event -> event.getLevel() == Level.WARN).toList();
  }
}
