package com.graduation.project.engine.core.messageBrokerConfig;

import com.fasterxml.jackson.databind.ObjectMapper;
import com.graduation.project.engine.rawEvent.model.RawEvent;
import java.util.Map;
import org.apache.kafka.clients.consumer.ConsumerConfig;
import org.apache.kafka.common.serialization.StringDeserializer;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.boot.autoconfigure.kafka.ConcurrentKafkaListenerContainerFactoryConfigurer;
import org.springframework.boot.autoconfigure.kafka.KafkaProperties;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.core.NestedExceptionUtils;
import org.springframework.kafka.config.ConcurrentKafkaListenerContainerFactory;
import org.springframework.kafka.core.ConsumerFactory;
import org.springframework.kafka.core.DefaultKafkaConsumerFactory;
import org.springframework.kafka.listener.ConsumerRecordRecoverer;
import org.springframework.kafka.listener.DefaultErrorHandler;
import org.springframework.kafka.support.serializer.ErrorHandlingDeserializer;
import org.springframework.kafka.support.serializer.JsonDeserializer;
import org.springframework.util.backoff.FixedBackOff;

/**
 * Consumer-side Kafka wiring for the single {@code rawEvents} listener.
 *
 * <h2>{@code spring.kafka.*} is configuration, not decoration</h2>
 *
 * <p>Both beans below still displace Spring Boot's own - {@link #consumerFactory} by type, because
 * Boot's is {@code @ConditionalOnMissingBean(ConsumerFactory.class)}, and
 * {@link #kafkaListenerContainerFactory} by taking literally the bean name Boot's is conditional
 * on - so Boot backs off and this class is the only thing that builds them. What it did NOT do was
 * any of the work Boot backed off from: the consumer map was assembled by hand and the container
 * factory never saw {@link ConcurrentKafkaListenerContainerFactoryConfigurer}. Every
 * {@code spring.kafka.consumer.*} and {@code spring.kafka.listener.*} key in every environment was
 * therefore inert - readable, plausible, and connected to nothing.
 *
 * <p>One extension point stays displaced, because it belongs to the bean Boot no longer creates: a
 * {@code DefaultKafkaConsumerFactoryCustomizer} bean would not be applied. There are none in this
 * application, and adding one is the moment to read this paragraph.
 *
 * <p>Now {@link KafkaProperties#buildConsumerProperties()} supplies the consumer map and the
 * configurer supplies the container settings, so those keys mean what Spring Boot's reference
 * documentation says they mean. Three decisions are still made here rather than in a file, and
 * each one is a decision, not an oversight:
 *
 * <ol>
 *   <li><b>{@code auto.offset.reset} defaults to {@code earliest}</b> - applied with
 *       {@code putIfAbsent}, so it is a default and not a second hardcoding. {@code KafkaProperties}
 *       leaves this key unset, which means the Kafka client default {@code latest}: a consumer
 *       group that has never committed silently discards everything already on the topic, so the
 *       first deployment against an existing topic, any group-id rename and any offset reset lose
 *       data without a log line. An operator who sets
 *       {@code spring.kafka.consumer.auto-offset-reset} still wins.</li>
 *   <li><b>The deserialisers are instances, and the matching properties are refused</b> - see
 *       below.</li>
 *   <li><b>The error handler is set AFTER {@code configure()}</b> - see below.</li>
 * </ol>
 *
 * <h2>Contract: a malformed event is dropped, never retried</h2>
 *
 * <p>The producer is an unauthenticated Python process on a topic with no schema registry, so
 * "bytes that are not a {@code RawEvent}" is a normal operating condition, not an incident. The
 * only acceptable response is to log the offset once and move on. Anything else - a retry loop,
 * or worse, no handling at all - converts one bad message into an outage of the entire pipeline,
 * because the topic has one partition and one consumer group.
 *
 * <p>{@code configure()} applies any single {@code CommonErrorHandler} bean in the context to the
 * factory. {@link #kafkaListenerContainerFactory} therefore sets its own error handler on the line
 * after, where it wins unconditionally. That ordering is the whole resolution of the conflict, and
 * it is load-bearing: spring-kafka's default is {@code FixedBackOff(0L, 9L)}, i.e. the listener is
 * re-invoked ten times for the same record with no pause between attempts - ten rounds of whatever
 * side effects it has already performed, which for a FALL event means ten emails to every user in
 * the database.
 *
 * <h2>Why {@link ErrorHandlingDeserializer} rather than an error handler alone</h2>
 *
 * <p>A deserialisation failure does not happen while a record is being delivered; it happens
 * inside {@code Consumer.poll()}, in {@code Fetcher.parseRecord}. No {@code ConsumerRecord} is
 * ever constructed, so a {@code CommonErrorHandler} has nothing to skip and the consumer's
 * position never advances. The next poll re-reads the same bytes and fails identically, forever.
 * spring-kafka says so itself, by throwing
 * {@code IllegalStateException: This error handler cannot process 'SerializationException's
 * directly; please consider configuring an 'ErrorHandlingDeserializer'}.
 *
 * <p>{@code ErrorHandlingDeserializer} moves the failure out of {@code poll()}: it returns a null
 * value and stores the exception in a header, the container detects that header before invoking
 * the listener, and the failure becomes an ordinary record-level error that the error handler
 * below can recover from and seek past.
 *
 * <h2>Deserialisers are passed as instances, so the two class properties are refused</h2>
 *
 * <p>{@link DefaultKafkaConsumerFactory} is given constructed deserialisers rather than classes.
 * When {@code KafkaConsumer} receives an instance it uses it as-is and never calls
 * {@code configure()} on it, which means {@code KEY_DESERIALIZER_CLASS_CONFIG},
 * {@code VALUE_DESERIALIZER_CLASS_CONFIG} and every {@code spring.json.*} property are ignored.
 * Everything that has to be configured on a deserialiser is therefore configured on the object -
 * see {@code useHeadersIfPresent} below.
 *
 * <p>{@code KafkaProperties} defaults both of those keys to {@code StringDeserializer}, so making
 * the properties live would have put two entries into the consumer map that read as settings and
 * are not. They are removed from the map, and a value that differs from that default is refused at
 * startup by {@link #rejectUnsupportedDeserializer}. Refusing is the point: this listener exists to
 * turn one specific wire format into {@code RawEvent}, and an operator who asks for a different
 * deserialiser has a misunderstanding that a silent no-op would preserve.
 *
 * <p>The one thing this cannot distinguish is "unset" from "explicitly set to
 * {@code StringDeserializer}", because the property carries Boot's default either way. Setting
 * {@code spring.kafka.consumer.value-deserializer} to {@code StringDeserializer} is accepted and
 * ignored; every other value fails the boot.
 */
@Configuration
public class KafkaConsumerConfig {

  private static final Logger LOGGER = LoggerFactory.getLogger(KafkaConsumerConfig.class);

  /**
   * The only deserialiser class this factory can be asked for, because it is the only one it
   * constructs. {@code KafkaProperties} defaults both {@code key-deserializer} and
   * {@code value-deserializer} to exactly this, which is how "unset" is recognised.
   */
  private static final Class<?> ONLY_SUPPORTED_DESERIALIZER = StringDeserializer.class;

  /**
   * Recovery for a record the pipeline cannot use: exactly one line, then the container seeks
   * past it. The offset is in the message because it is the only way to find the payload again
   * with {@code kafka-console-consumer --partition --offset}; the payload itself is not logged,
   * since it is unvalidated input of unbounded size.
   */
  private static final ConsumerRecordRecoverer DROP_MALFORMED_RECORD = (record, exception) -> {
    // The exception handed to a recoverer is a ListenerExecutionFailedException whose own
    // message is the useless constant "Listener failed"; the reason the record was rejected is
    // always further down the chain.
    Throwable cause = NestedExceptionUtils.getMostSpecificCause(exception);
    LOGGER.warn("Dropping malformed record from {}-{} at offset {}: {}: {}",
        record.topic(), record.partition(), record.offset(),
        cause.getClass().getSimpleName(), cause.getMessage());
  };

  @Bean
  public ConsumerFactory<String, RawEvent> consumerFactory(KafkaProperties kafkaProperties) {
    KafkaProperties.Consumer consumerProperties = kafkaProperties.getConsumer();
    rejectUnsupportedDeserializer("key-deserializer", consumerProperties.getKeyDeserializer());
    rejectUnsupportedDeserializer("value-deserializer", consumerProperties.getValueDeserializer());

    // Boot's own map, so spring.kafka.bootstrap-servers, spring.kafka.consumer.* and
    // spring.kafka.properties.* all arrive. It is a fresh HashMap on every call, so mutating it
    // affects nothing else.
    Map<String, Object> props = kafkaProperties.buildConsumerProperties();
    props.remove(ConsumerConfig.KEY_DESERIALIZER_CLASS_CONFIG);
    props.remove(ConsumerConfig.VALUE_DESERIALIZER_CLASS_CONFIG);
    props.putIfAbsent(ConsumerConfig.AUTO_OFFSET_RESET_CONFIG, "earliest");

    // useHeadersIfPresent = false. The Python producer sends no __TypeId__ header, so today the
    // deserialiser only reaches the configured target type by falling back to it. That fallback
    // is fragile - any producer that does send a type header would override RawEvent - and the
    // equivalent USE_TYPE_INFO_HEADERS property would be ignored on a constructed instance, so
    // it is pinned on the object instead.
    JsonDeserializer<RawEvent> jsonDeserializer =
        new JsonDeserializer<>(RawEvent.class, new ObjectMapper(), false);

    return new DefaultKafkaConsumerFactory<>(props, new StringDeserializer(),
        new ErrorHandlingDeserializer<>(jsonDeserializer));
  }

  @Bean
  public ConcurrentKafkaListenerContainerFactory<String, RawEvent> kafkaListenerContainerFactory(
      ConcurrentKafkaListenerContainerFactoryConfigurer configurer,
      ConsumerFactory<String, RawEvent> consumerFactory) {

    ConcurrentKafkaListenerContainerFactory<String, RawEvent> factory =
        new ConcurrentKafkaListenerContainerFactory<>();
    // Sets the consumer factory and applies every spring.kafka.listener.* key: concurrency,
    // ack-mode, poll-timeout, client-id, the idle/monitor intervals and missing-topics-fatal.
    configurer.configure(erased(factory), erased(consumerFactory));

    // AFTER configure(), deliberately - see the class javadoc. FixedBackOff(0, 0) = one attempt,
    // no retries. Nothing about a structurally invalid event becomes valid on the second attempt,
    // so there is nothing to retry.
    factory.setCommonErrorHandler(
        new DefaultErrorHandler(DROP_MALFORMED_RECORD, new FixedBackOff(0L, 0L)));
    return factory;
  }

  /**
   * Fails the boot when configuration asks for a deserialiser this factory does not build.
   *
   * @param property the {@code spring.kafka.consumer.*} key, named so the message is actionable
   * @param configured the class bound from that key - never null, {@code KafkaProperties} defaults
   *     both keys to {@link #ONLY_SUPPORTED_DESERIALIZER}
   */
  private static void rejectUnsupportedDeserializer(String property, Class<?> configured) {
    if (!ONLY_SUPPORTED_DESERIALIZER.equals(configured)) {
      throw new IllegalStateException(
          "spring.kafka.consumer." + property + " is set to " + configured.getName()
              + ", which this application cannot honour: KafkaConsumerConfig constructs its own "
              + "deserialiser instances (StringDeserializer keys, ErrorHandlingDeserializer around "
              + "a RawEvent JsonDeserializer for values), and KafkaConsumer never calls configure() "
              + "on a supplied instance. Remove the property rather than expecting it to apply.");
    }
  }

  /**
   * Drops the type arguments so the configurer's {@code <Object, Object>} signature accepts these
   * {@code <String, RawEvent>} beans.
   *
   * <p>Unchecked and safe: the configurer only ever calls setters, and generics on both types are
   * erased at runtime. The beans keep their real type arguments because
   * {@code RawEventListenerIT} injects {@code ConsumerFactory<String, RawEvent>} by generic type,
   * which a bean declared as {@code <Object, Object>} would not satisfy.
   */
  @SuppressWarnings("unchecked")
  private static <T> T erased(Object typed) {
    return (T) typed;
  }
}
